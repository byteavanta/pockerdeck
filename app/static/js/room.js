class RoomApp {
  constructor(roomId, isCreator, cards, isSpectator) {
    this.roomId = roomId;
    this.isCreator = isCreator;
    this.isSpectator = isSpectator || false;
    this.cards = cards;
    this.userName = null;
    this.userRole = 'user';
    this.isAdmin = false;
    this.ws = null;
    this.myVote = null;
    this.shouldReconnect = true;
    this.editingBliIndex = null;
    this.lastState = null;
    this.confirmingDeleteBli = null;
    this.renamingUser = null;
    this._timerInterval = null;
    this._timerDuration = 60;
    this._timerLastEnd = null;
  }

  init() {
    var self = this;
    document.getElementById('room-id-text').innerHTML =
      '<span class="room-id-badge">' + this.roomId + '</span>';

    var savedSpectator = sessionStorage.getItem('spectator_' + this.roomId) === '1';
    if (this.isCreator || this.isSpectator || savedSpectator) {
      var roleSelector = document.getElementById('role-selector');
      if (roleSelector) roleSelector.style.display = 'none';
    }

    var nameInput = document.getElementById('name-input');
    nameInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') self.submitName();
    });
    nameInput.addEventListener('input', function () {
      nameInput.classList.remove('error');
    });

    document.getElementById('story-text').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        self.setStory(document.getElementById('story-btn'));
      }
    });

    document.getElementById('bli-room-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); self.addBliInRoom(); }
    });

    // Close rename popover on outside click
    document.addEventListener('click', function (e) {
      if (self.renamingUser && !e.target.closest('.rename-popover') && !e.target.closest('.btn-icon')) {
        self.renamingUser = null;
        self._renderParticipantsDOM(self.lastState);
      }
    });

    this.renderCards();

    var saved = sessionStorage.getItem('name_' + this.roomId);
    if (saved) {
      this.userName = saved;
      this.userRole = sessionStorage.getItem('role_' + this.roomId) || 'user';
      if (sessionStorage.getItem('spectator_' + this.roomId) === '1') {
        this.isSpectator = true;
      }
      document.getElementById('name-modal').classList.add('hidden');
      this.showApp();
      this.connect();
    } else {
      setTimeout(function () { nameInput.focus(); }, 50);
    }

    window.addEventListener('beforeunload', function () {
      self.shouldReconnect = false;
      if (self.ws) self.ws.close();
    });
  }

  // ── Connection ──────────────────────────────────────────────────────────────

  submitNameAsSpectator() {
    this.isSpectator = true;
    this.submitName();
  }

  submitName() {
    var input = document.getElementById('name-input');
    var name = input.value.trim();
    if (!name) {
      input.classList.add('error');
      input.focus();
      return;
    }
    var roleInput = document.querySelector('input[name="role"]:checked');
    this.userName = name;
    if (this.isSpectator) {
      this.userRole = 'viewer';
    } else {
      this.userRole = this.isCreator ? 'user' : (roleInput ? roleInput.value : 'user');
    }
    sessionStorage.setItem('name_' + this.roomId, name);
    sessionStorage.setItem('role_' + this.roomId, this.userRole);
    if (this.isSpectator) {
      sessionStorage.setItem('spectator_' + this.roomId, '1');
    }
    document.getElementById('name-modal').classList.add('hidden');
    this.showApp();
    this.connect();
  }

  showApp() {
    document.getElementById('app').classList.remove('hidden');
  }

  connect() {
    var self = this;
    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = protocol + '//' + location.host + '/ws/' + this.roomId + '/' + encodeURIComponent(this.userName) + '?role=' + encodeURIComponent(this.userRole);
    this.setStatus('connecting', 'Connecting…');
    this.ws = new WebSocket(url);

    this.ws.onopen = function () {
      self.setStatus('connected', 'Connected');
    };

    this.ws.onmessage = function (event) {
      var state = JSON.parse(event.data);
      if (state.renamed && state.renamed.from === self.userName) {
        self.userName = state.renamed.to;
        sessionStorage.setItem('name_' + self.roomId, self.userName);
      }
      self.render(state);
    };

    this.ws.onerror = function () {
      self.setStatus('disconnected', 'Connection error');
    };

    this.ws.onclose = function (event) {
      if (event.code === 4004) {
        self.shouldReconnect = false;
        self.showToast('This room no longer exists.', 'error');
        setTimeout(function () { window.location.href = '/'; }, 2000);
        return;
      }
      if (event.code === 4005) {
        self.shouldReconnect = false;
        self.showToast('You were removed from the room.', 'warning');
        setTimeout(function () { window.location.href = '/'; }, 2000);
        return;
      }
      self.setStatus('disconnected', 'Reconnecting…');
      if (self.shouldReconnect) setTimeout(function () { self.connect(); }, 2500);
    };
  }

  send(data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(data));
    return true;
  }

  setStatus(cls, text) {
    var el = document.getElementById('conn-status');
    el.className = 'status-badge ' + cls;
    el.textContent = text;
  }

  // ── Toasts ──────────────────────────────────────────────────────────────────

  showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    container.appendChild(toast);

    var DURATION = 3500;
    var FADE = 350;
    setTimeout(function () {
      toast.classList.add('expiring');
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, FADE);
    }, DURATION - FADE);
  }

  // ── Rendering ───────────────────────────────────────────────────────────────

  render(state) {
    if (state.users[this.userName]) {
      this.userRole = state.users[this.userName].role;
    }
    this.isAdmin = (state.admin === this.userName);
    if (!state.revealed && state.users[this.userName] && state.users[this.userName].vote === null) {
      this.myVote = null;
    }

    // Toast diffing
    if (this.lastState) {
      this._diffToasts(state);
    }

    var prevState = this.lastState;
    this.lastState = state;

    this.renderBacklog(state);
    this.renderParticipants(state, prevState);
    this.renderProgress(state);
    this.renderControls(state);
    this.renderResults(state);
    this.renderDistribution(state);
    this.renderTimer(state);
    this.syncStory(state);
  }

  _diffToasts(state) {
    var prev = this.lastState;

    // User joined / left
    var prevUsers = Object.keys(prev.users);
    var currUsers = Object.keys(state.users);
    var self = this;
    currUsers.forEach(function (name) {
      if (prevUsers.indexOf(name) === -1 && name !== self.userName) {
        self.showToast('👋 ' + name + ' joined', 'info');
      }
    });
    prevUsers.forEach(function (name) {
      if (currUsers.indexOf(name) === -1) {
        self.showToast(name + ' left', 'info');
      }
    });

    // Renamed
    if (state.renamed) {
      this.showToast('✏️ ' + state.renamed.from + ' → ' + state.renamed.to, 'info');
    }

    // Reveal
    if (!prev.revealed && state.revealed) {
      this.showToast('🃏 Votes revealed!', 'success');
    }

    // New round
    if (prev.revealed && !state.revealed) {
      this.showToast('🔄 New round started', 'info');
    }

    // Timer stopped — only toast if it was stopped early (interval already toasts on natural expiry)
    if (prev.timer_active && !state.timer_active) {
      var wasExpired = prev.timer_end && (Date.now() / 1000) >= prev.timer_end;
      if (!wasExpired) this.showToast('⏱ Timer stopped', 'info');
    }
  }

  renderCards() {
    var self = this;
    var grid = document.getElementById('cards-grid');
    this.cards.forEach(function (value) {
      var btn = document.createElement('button');
      btn.className = 'vote-card';
      btn.dataset.value = value;
      btn.textContent = value;
      btn.addEventListener('click', function () { self.vote(value); });
      grid.appendChild(btn);
    });
  }

  // Diff-based participants render to preserve DOM nodes for flip animation
  renderParticipants(state, prevState) {
    var isRevealTransition = prevState && !prevState.revealed && state.revealed;
    this._renderParticipantsDOM(state, isRevealTransition);
  }

  _renderParticipantsDOM(state, isRevealTransition) {
    var self = this;
    var container = document.getElementById('participants');
    var entries = state ? Object.entries(state.users) : [];

    if (!state || entries.length === 0) {
      container.innerHTML = '';
      var msg = document.createElement('p');
      msg.className = 'empty-state';
      msg.textContent = 'No participants yet';
      container.appendChild(msg);
      return;
    }

    var isAdmin = this.isAdmin;
    var minVote = null;
    var maxVote = null;
    if (state.revealed) {
      var nums = Object.values(state.users)
        .filter(function (u) { return u.role !== 'viewer' && u.vote !== null && u.vote !== undefined && !isNaN(Number(u.vote)); })
        .map(function (u) { return Number(u.vote); });
      if (nums.length > 1) {
        var mn = Math.min.apply(null, nums);
        var mx = Math.max.apply(null, nums);
        if (mn !== mx) { minVote = mn; maxVote = mx; }
      }
    }

    // Remove cards for users who left
    var existing = container.querySelectorAll('.participant-card[data-name]');
    existing.forEach(function (el) {
      if (!state.users[el.dataset.name]) el.parentNode.removeChild(el);
    });

    // Remove empty-state message if it exists
    var emptyMsg = container.querySelector('.empty-state');
    if (emptyMsg) container.removeChild(emptyMsg);

    entries.forEach(function (entry, idx) {
      var name = entry[0];
      var info = entry[1];
      var isViewer = info.role === 'viewer';
      var isMe = name === self.userName;

      var existingCard = container.querySelector('.participant-card[data-name="' + CSS.escape(name) + '"]');

      if (!existingCard) {
        // Create new card
        var card = self._buildParticipantCard(name, info, isViewer, isAdmin, isMe, state, minVote, maxVote);
        // Insert in position
        var allCards = container.querySelectorAll('.participant-card[data-name]');
        var insertBefore = allCards[idx] || null;
        container.insertBefore(card, insertBefore);
      } else {
        // Update existing card in place
        self._updateParticipantCard(existingCard, name, info, isViewer, isAdmin, isMe, state, minVote, maxVote, isRevealTransition, idx);
      }
    });

    // If renaming, show popover
    if (self.renamingUser) {
      var targetCard = container.querySelector('.participant-card[data-name="' + CSS.escape(self.renamingUser) + '"]');
      if (targetCard && !targetCard.querySelector('.rename-popover')) {
        self._attachRenamePopover(targetCard, self.renamingUser);
      }
    }
  }

  _buildParticipantCard(name, info, isViewer, isAdmin, isMe, state, minVote, maxVote) {
    var self = this;
    var card = document.createElement('div');
    card.className = 'participant-card';
    card.dataset.name = name;

    var wrap = document.createElement('div');
    wrap.className = 'p-badge-wrap';

    var inner = document.createElement('div');
    inner.className = 'p-badge-inner';

    var backFace = document.createElement('div');
    backFace.className = 'p-badge-face p-badge-back';
    var frontFace = document.createElement('div');
    frontFace.className = 'p-badge-face p-badge-front';

    inner.appendChild(backFace);
    inner.appendChild(frontFace);
    wrap.appendChild(inner);
    card.appendChild(wrap);

    var nameEl = document.createElement('div');
    nameEl.className = 'p-name' + (isMe ? ' me' : '');
    nameEl.textContent = name + (info.role === 'admin' ? ' 👑' : '');
    card.appendChild(nameEl);

    this._setBadgeState(backFace, frontFace, inner, info, isViewer, state.revealed, false);
    this._setVoteLabel(card, name, info, isViewer, state, minVote, maxVote);
    this._setAdminControls(card, name, isAdmin, isMe);

    return card;
  }

  _updateParticipantCard(card, name, info, isViewer, isAdmin, isMe, state, minVote, maxVote, isRevealTransition, idx) {
    var self = this;
    var inner = card.querySelector('.p-badge-inner');
    var backFace = card.querySelector('.p-badge-back');
    var frontFace = card.querySelector('.p-badge-front');

    this._setBadgeState(backFace, frontFace, inner, info, isViewer, state.revealed, isRevealTransition, idx);
    this._setVoteLabel(card, name, info, isViewer, state, minVote, maxVote);

    // Update name
    var nameEl = card.querySelector('.p-name');
    if (nameEl) {
      nameEl.className = 'p-name' + (isMe ? ' me' : '');
      nameEl.textContent = name + (info.role === 'admin' ? ' 👑' : '');
    }

    // Update admin controls
    var actions = card.querySelector('.p-actions');
    if (isAdmin && !isMe) {
      if (!actions) this._setAdminControls(card, name, isAdmin, isMe);
    } else {
      if (actions) card.removeChild(actions);
    }
  }

  _setBadgeState(backFace, frontFace, inner, info, isViewer, revealed, animate, idx) {
    var isNA = info.vote === null || info.vote === undefined;

    if (isViewer) {
      backFace.className = 'p-badge-face p-badge-back viewer-badge';
      backFace.textContent = '👁';
      frontFace.className = 'p-badge-face p-badge-front';
      frontFace.textContent = '';
      inner.classList.remove('flipped');
      return;
    }

    if (revealed) {
      // Front face shows the vote
      frontFace.className = 'p-badge-face p-badge-front revealed' + (isNA ? ' no-vote' : '');
      frontFace.textContent = isNA ? '–' : info.vote;
      // Back face stays with previous state
      if (animate) {
        var delay = (idx || 0) * 65;
        setTimeout(function () { inner.classList.add('flipped'); }, delay);
      } else {
        inner.classList.add('flipped');
      }
    } else {
      // Back face
      backFace.className = 'p-badge-face p-badge-back ' + (info.vote === 'voted' ? 'voted' : 'waiting');
      backFace.textContent = info.vote === 'voted' ? '✓' : '…';
      frontFace.textContent = '';
      inner.classList.remove('flipped');
    }
  }

  _setVoteLabel(card, name, info, isViewer, state, minVote, maxVote) {
    // Remove existing label
    var existing = card.querySelector('.vote-label');
    if (existing) card.removeChild(existing);

    if (!state.revealed || isViewer || minVote === null) return;
    var voteNum = Number(info.vote);
    if (isNaN(voteNum)) return;
    if (voteNum !== minVote && voteNum !== maxVote) return;

    var label = document.createElement('span');
    label.className = 'vote-label ' + (voteNum === minVote ? 'vote-label--min' : 'vote-label--max');
    label.textContent = voteNum === minVote ? 'min' : 'max';
    card.appendChild(label);
  }

  _setAdminControls(card, name, isAdmin, isMe) {
    var self = this;
    var existing = card.querySelector('.p-actions');
    if (existing) card.removeChild(existing);
    if (!isAdmin || isMe) return;

    var actions = document.createElement('div');
    actions.className = 'p-actions';

    var renameBtn = document.createElement('button');
    renameBtn.className = 'btn-icon';
    renameBtn.title = 'Rename';
    renameBtn.textContent = '✏️';
    renameBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      self.renamingUser = name;
      self._renderParticipantsDOM(self.lastState);
    });

    var kickBtn = document.createElement('button');
    kickBtn.className = 'btn-icon btn-icon-danger';
    kickBtn.title = 'Kick';
    kickBtn.textContent = '✕';
    kickBtn.addEventListener('click', function () { self.kickUser(name); });

    actions.appendChild(renameBtn);
    actions.appendChild(kickBtn);
    card.appendChild(actions);
  }

  _attachRenamePopover(card, targetName) {
    var self = this;
    var popover = document.createElement('div');
    popover.className = 'rename-popover';

    var input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'New name…';
    input.maxLength = 32;
    input.value = targetName;
    popover.appendChild(input);

    var btnRow = document.createElement('div');
    btnRow.className = 'rename-popover-actions';

    var okBtn = document.createElement('button');
    okBtn.className = 'btn btn-primary';
    okBtn.textContent = '✓';
    okBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var newName = input.value.trim();
      if (!newName) return;
      self.send({ action: 'rename_user', target: targetName, new_name: newName });
      self.renamingUser = null;
    });

    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = '✕';
    cancelBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      self.renamingUser = null;
      self._renderParticipantsDOM(self.lastState);
    });

    btnRow.appendChild(okBtn);
    btnRow.appendChild(cancelBtn);
    popover.appendChild(btnRow);
    card.appendChild(popover);

    setTimeout(function () {
      input.focus();
      input.select();
    }, 0);

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); okBtn.click(); }
      if (e.key === 'Escape') { cancelBtn.click(); }
    });
    input.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  renderProgress(state) {
    var fill = document.getElementById('vote-progress-fill');
    var text = document.getElementById('vote-progress-text');
    if (state.revealed) {
      fill.style.width = '0%';
      text.textContent = '';
      return;
    }
    var voters = Object.values(state.users).filter(function (u) { return u.role !== 'viewer'; });
    var voted  = voters.filter(function (u) { return u.vote === 'voted'; }).length;
    var total  = voters.length;
    var pct    = total > 0 ? Math.round((voted / total) * 100) : 0;
    fill.style.width = pct + '%';
    text.textContent = total > 0 ? voted + ' of ' + total + ' voted' : '';
  }

  renderControls(state) {
    var cardsPanel    = document.getElementById('cards-panel');
    var revealBtn     = document.getElementById('reveal-btn');
    var resetBtn      = document.getElementById('reset-btn');
    var storyBtn      = document.getElementById('story-btn');
    var storyText     = document.getElementById('story-text');
    var timerPicker = document.getElementById('timer-picker');

    var isViewer = (this.userRole === 'viewer');
    var canAct   = !isViewer || this.isAdmin;

    storyText.readOnly = isViewer && !this.isAdmin;
    storyBtn.classList.toggle('hidden', isViewer && !this.isAdmin);

    if (state.revealed) {
      cardsPanel.classList.add('hidden');
      revealBtn.classList.add('hidden');
      resetBtn.classList.toggle('hidden', !canAct);
      timerPicker.classList.add('hidden');
    } else {
      cardsPanel.classList.toggle('hidden', isViewer);
      revealBtn.classList.toggle('hidden', !canAct);
      resetBtn.classList.add('hidden');
      timerPicker.classList.toggle('hidden', !isAdmin || state.timer_active);

      if (!isViewer) {
        var myVote = this.myVote;
        document.querySelectorAll('.vote-card').forEach(function (card) {
          card.classList.toggle('selected', card.dataset.value === myVote);
        });
      }
    }
  }

  renderResults(state) {
    var panel = document.getElementById('results-panel');
    if (!state.revealed) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');

    var numeric = Object.values(state.users)
      .filter(function (u) { return u.role !== 'viewer' && u.vote !== null && u.vote !== undefined && !isNaN(parseFloat(u.vote)); })
      .map(function (u) { return Number(u.vote); });

    if (numeric.length > 0) {
      var sum = numeric.reduce(function (a, b) { return a + b; }, 0);
      var avg = sum / numeric.length;
      document.getElementById('res-avg').textContent = Number.isInteger(avg) ? avg : avg.toFixed(1);
      document.getElementById('res-min').textContent = Math.min.apply(null, numeric);
      document.getElementById('res-max').textContent = Math.max.apply(null, numeric);
    } else {
      ['res-avg', 'res-min', 'res-max'].forEach(function (id) {
        document.getElementById(id).textContent = '–';
      });
    }
  }

  renderDistribution(state) {
    var container = document.getElementById('vote-distribution');
    if (!state.revealed) {
      container.innerHTML = '';
      return;
    }

    // Count votes
    var counts = {};
    Object.values(state.users).forEach(function (u) {
      if (u.role === 'viewer' || u.vote === null || u.vote === undefined) return;
      var v = String(u.vote);
      counts[v] = (counts[v] || 0) + 1;
    });

    var entries = Object.entries(counts);
    if (entries.length === 0) { container.innerHTML = ''; return; }

    // Sort: numeric first, then string
    entries.sort(function (a, b) {
      var an = parseFloat(a[0]), bn = parseFloat(b[0]);
      var aNum = !isNaN(an), bNum = !isNaN(bn);
      if (aNum && bNum) return an - bn;
      if (aNum) return -1;
      if (bNum) return 1;
      return a[0].localeCompare(b[0]);
    });

    var maxCount = Math.max.apply(null, entries.map(function (e) { return e[1]; }));

    container.innerHTML = '';
    entries.forEach(function (e) {
      var val = e[0], count = e[1];
      var row = document.createElement('div');
      row.className = 'dist-row';

      var lbl = document.createElement('div');
      lbl.className = 'dist-label';
      lbl.textContent = val;

      var barWrap = document.createElement('div');
      barWrap.className = 'dist-bar-wrap';
      var bar = document.createElement('div');
      bar.className = 'dist-bar';
      bar.style.width = '0%';
      barWrap.appendChild(bar);

      var cnt = document.createElement('div');
      cnt.className = 'dist-count';
      cnt.textContent = count + 'x';

      row.appendChild(lbl);
      row.appendChild(barWrap);
      row.appendChild(cnt);
      container.appendChild(row);

      // Animate bar in after paint
      requestAnimationFrame(function () {
        bar.style.width = Math.round((count / maxCount) * 100) + '%';
      });
    });
  }

  renderTimer(state) {
    var self = this;
    var panel       = document.getElementById('timer-panel');
    var display     = document.getElementById('timer-display');
    var ringFill    = document.getElementById('timer-ring-fill');
    var stopBtn     = document.getElementById('timer-stop-btn');
    var isAdmin     = (this.userRole === 'admin');

    if (!state.timer_active || !state.timer_end) {
      panel.classList.add('hidden');
      stopBtn.classList.add('hidden');
      this._clearTimerInterval();
      return;
    }

    panel.classList.remove('hidden');
    stopBtn.classList.toggle('hidden', !isAdmin);

    // Infer original duration from first time we see this timer end time
    if (this._timerLastEnd !== state.timer_end) {
      this._timerLastEnd = state.timer_end;
      // Estimate duration from remaining time (snap to nearest 10s preset)
      var remaining = state.timer_end - (Date.now() / 1000);
      var presets = [30, 60, 90, 120, 180, 300];
      this._timerDuration = presets.reduce(function (prev, cur) {
        return Math.abs(cur - remaining) < Math.abs(prev - remaining) ? cur : prev;
      }, 60);
      // But clamp to at least remaining
      if (this._timerDuration < remaining) this._timerDuration = Math.ceil(remaining / 10) * 10;
    }

    this._clearTimerInterval();
    this._timerInterval = setInterval(function () {
      var now      = Date.now() / 1000;
      var left     = Math.max(0, state.timer_end - now);
      var mins     = Math.floor(left / 60);
      var secs     = Math.floor(left % 60);
      var urgent   = left <= 10;
      var circumference = 175.9; // 2π×28

      display.textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
      display.classList.toggle('urgent', urgent);
      ringFill.classList.toggle('urgent', urgent);

      var frac = self._timerDuration > 0 ? left / self._timerDuration : 0;
      ringFill.style.strokeDashoffset = circumference * (1 - frac);

      if (left <= 0) {
        self._clearTimerInterval();
        self.showToast("⏱ Time's up!", 'warning');
        panel.classList.add('hidden');
        stopBtn.classList.add('hidden');
        // Tell the server the timer is done so late-joiners don't see a stale timer
        if (self.userRole === 'admin') self.send({ action: 'stop_timer' });
      }
    }, 200);
  }

  _clearTimerInterval() {
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }
  }

  renderBacklog(state) {
    var self = this;
    this.lastState = state;
    var list     = document.getElementById('backlog-list');
    var addRow   = document.getElementById('backlog-add-row');
    var emptyMsg = document.getElementById('backlog-empty');
    var backlog = state.backlog || [];
    var isAdmin = this.isAdmin;

    addRow.classList.toggle('hidden', !isAdmin);
    list.innerHTML = '';

    if (backlog.length === 0) {
      emptyMsg.classList.remove('hidden');
    } else {
      emptyMsg.classList.add('hidden');
    }

    backlog.forEach(function (item, idx) {
      var isActive = state.active_bli === idx;
      var isDone   = item.done;

      var li = document.createElement('li');
      li.className = 'backlog-item' + (isActive ? ' active' : '') + (isDone ? ' done' : '');

      var num = document.createElement('span');
      num.className = 'bli-num';
      num.textContent = (idx + 1) + '.';

      var title = document.createElement('span');
      title.className = 'bli-title';
      title.textContent = item.title;

      li.appendChild(num);
      li.appendChild(title);

      if (isActive) {
        var activeTag = document.createElement('span');
        activeTag.className = 'bli-tag active-tag';
        activeTag.textContent = '▶ Voting';
        li.appendChild(activeTag);
        if (isAdmin) {
          var doneBtn = document.createElement('button');
          doneBtn.className = 'btn btn-secondary bli-vote-btn';
          doneBtn.textContent = '✓ Mark Done';
          (function (i) { doneBtn.onclick = function () { self.markBliDone(i); }; }(idx));
          li.appendChild(doneBtn);
        }
      } else if (isDone) {
        var doneTag = document.createElement('span');
        doneTag.className = 'bli-tag done-tag';
        doneTag.textContent = '✓ Done';
        li.appendChild(doneTag);
      } else if (isAdmin) {
        var voteBtn = document.createElement('button');
        voteBtn.className = 'btn btn-secondary bli-vote-btn';
        voteBtn.textContent = 'Vote on this';
        (function (i) { voteBtn.onclick = function () { self.selectBli(i); }; }(idx));
        li.appendChild(voteBtn);
      }

      if (isAdmin) {
        var actions = document.createElement('span');
        actions.className = 'bli-actions';

        var editBtn = document.createElement('button');
        editBtn.className = 'btn-icon';
        editBtn.title = 'Edit';
        editBtn.textContent = '✏️';
        (function (i) { editBtn.onclick = function () { self.startEditBli(i); }; }(idx));

        var delBtn = document.createElement('button');
        delBtn.className = 'btn-icon btn-icon-danger';
        delBtn.title = 'Delete';
        delBtn.textContent = '🗑';
        (function (i) { delBtn.onclick = function () { self.confirmDeleteBli(i); }; }(idx));

        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        li.appendChild(actions);
      }

      // Inline delete confirmation
      if (isAdmin && self.confirmingDeleteBli === idx) {
        li.classList.add('bli-confirming-delete');
        var confirmRow = document.createElement('div');
        confirmRow.className = 'bli-delete-confirm';
        var confirmLabel = document.createElement('span');
        confirmLabel.className = 'bli-delete-label';
        confirmLabel.textContent = 'Delete?';
        var yesBtn = document.createElement('button');
        yesBtn.className = 'btn btn-danger-sm';
        yesBtn.textContent = 'Yes';
        (function (i) { yesBtn.onclick = function () { self.deleteBli(i); }; }(idx));
        var noBtn = document.createElement('button');
        noBtn.className = 'btn btn-secondary bli-edit-cancel';
        noBtn.textContent = 'No';
        noBtn.onclick = function () { self.cancelDeleteBli(); };
        confirmRow.appendChild(confirmLabel);
        confirmRow.appendChild(yesBtn);
        confirmRow.appendChild(noBtn);
        li.appendChild(confirmRow);
      }

      // Inline edit
      if (isAdmin && self.editingBliIndex === idx) {
        li.classList.add('bli-editing');
        title.classList.add('hidden');
        var editRow = document.createElement('span');
        editRow.className = 'bli-edit-inline';
        var editInput = document.createElement('input');
        editInput.type = 'text';
        editInput.className = 'bli-edit-input';
        editInput.value = item.title;
        editInput.maxLength = 200;
        var saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-primary bli-edit-save';
        saveBtn.textContent = '✓';
        var cancelBtn2 = document.createElement('button');
        cancelBtn2.className = 'btn btn-secondary bli-edit-cancel';
        cancelBtn2.textContent = '✕';
        (function (i, inp) {
          saveBtn.onclick = function () { self.submitEditBli(i, inp.value); };
          cancelBtn2.onclick = function () { self.cancelEditBli(); };
          editInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter')  { e.preventDefault(); self.submitEditBli(i, inp.value); }
            if (e.key === 'Escape') { self.cancelEditBli(); }
          });
        }(idx, editInput));
        editRow.appendChild(editInput);
        editRow.appendChild(saveBtn);
        editRow.appendChild(cancelBtn2);
        li.insertBefore(editRow, title.nextSibling);
        setTimeout(function () { editInput.focus(); editInput.select(); }, 0);
      }

      list.appendChild(li);
    });
  }

  renderBacklogInline() {
    if (this.lastState) this.renderBacklog(this.lastState);
  }

  syncStory(state) {
    var el = document.getElementById('story-text');
    if (document.activeElement !== el) el.value = state.story || '';
  }

  // ── Actions ─────────────────────────────────────────────────────────────────

  vote(value) {
    // Viewers cannot vote; also enforced server-side in Room.vote()
    if (this.userRole === 'viewer') return;
    if (this.myVote === value) {
      this.myVote = null;
      this.send({ action: 'vote', value: null });
    } else {
      this.myVote = value;
      this.send({ action: 'vote', value: value });
    }
    var myVote = this.myVote;
    document.querySelectorAll('.vote-card').forEach(function (card) {
      card.classList.toggle('selected', card.dataset.value === myVote);
    });
  }

  revealVotes()   { this.send({ action: 'reveal' }); }

  newRound() {
    this.myVote = null;
    var story = document.getElementById('story-text').value;
    var btn = document.getElementById('reset-btn');
    if (btn) {
      if (!btn._flashTimer) btn._origHTML = btn.innerHTML;
      else clearTimeout(btn._flashTimer);
      btn.innerHTML = '✓ Round reset';
      btn.classList.add('btn-success-flash');
      btn._flashTimer = setTimeout(function () {
        btn.innerHTML = btn._origHTML;
        btn.classList.remove('btn-success-flash');
        btn._flashTimer = null;
      }, 1500);
    }
    this.send({ action: 'reset', story: story });
  }

  kickUser(target)   { this.send({ action: 'kick', target: target }); }

  startTimer(duration) {
    duration = duration || 60;
    this._clearTimerInterval();
    this._timerLastEnd = null;
    this._timerDuration = duration;
    this.send({ action: 'start_timer', duration: duration });
  }

  stopTimer()        { this.send({ action: 'stop_timer' }); }

  setStory(btn) {
    var story = document.getElementById('story-text').value;
    this.send({ action: 'set_story', story: story });
    if (!btn) return;
    if (btn._flashTimer) clearTimeout(btn._flashTimer);
    else btn._origHTML = btn.innerHTML;
    btn.innerHTML = '✓ Updated';
    btn.classList.add('btn-success-flash');
    btn._flashTimer = setTimeout(function () {
      btn.innerHTML = btn._origHTML;
      btn.classList.remove('btn-success-flash');
      btn._flashTimer = null;
    }, 2000);
  }

  copyLink() {
    var btn = document.getElementById('copy-btn');
    var cleanUrl = location.origin + location.pathname;
    function showSuccess() {
      if (btn._flashTimer) clearTimeout(btn._flashTimer);
      else btn._origHTML = btn.innerHTML;
      btn.innerHTML = '✓ Copied!';
      btn.classList.add('btn-success-flash');
      btn._flashTimer = setTimeout(function () {
        btn.innerHTML = btn._origHTML;
        btn.classList.remove('btn-success-flash');
        btn._flashTimer = null;
      }, 2000);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(cleanUrl).then(showSuccess);
    } else {
      var ta = document.createElement('textarea');
      ta.value = cleanUrl;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showSuccess();
    }
  }

  // ── Backlog actions ──────────────────────────────────────────────────────────

  selectBli(index)     { this.send({ action: 'select_bli',   index: index }); }
  markBliDone(index)   { this.send({ action: 'mark_bli_done', index: index }); }

  addBliInRoom() {
    var input = document.getElementById('bli-room-input');
    var title = input.value.trim();
    if (!title) return;
    this.send({ action: 'add_bli', title: title });
    input.value = '';
    input.focus();
  }

  startEditBli(index)  { this.confirmingDeleteBli = null; this.editingBliIndex = index; this.renderBacklogInline(); }

  submitEditBli(index, value) {
    var title = value.trim();
    if (!title) return;
    this.editingBliIndex = null;
    this.send({ action: 'edit_bli', index: index, title: title });
  }

  cancelEditBli()      { this.editingBliIndex = null; this.renderBacklogInline(); }

  confirmDeleteBli(index) { this.editingBliIndex = null; this.confirmingDeleteBli = index; this.renderBacklogInline(); }
  cancelDeleteBli()       { this.confirmingDeleteBli = null; this.renderBacklogInline(); }

  deleteBli(index) {
    this.confirmingDeleteBli = null;
    this.send({ action: 'delete_bli', index: index });
  }
}
