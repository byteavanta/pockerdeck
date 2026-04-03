class RoomApp {
  constructor(roomId, isCreator, cards) {
    this.roomId = roomId;
    this.isCreator = isCreator;
    this.cards = cards;
    this.userName = null;
    this.userRole = 'user';
    this.ws = null;
    this.myVote = null;
    this.shouldReconnect = true;
    this.editingBliIndex = null;
    this.lastState = null;
    this.confirmingDeleteBli = null;
  }

  init() {
    var self = this;
    document.getElementById('room-id-text').textContent = this.roomId;

    if (this.isCreator) {
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
      if (e.key === 'Enter') {
        e.preventDefault();
        self.addBliInRoom();
      }
    });

    this.renderCards();

    var saved = sessionStorage.getItem('name_' + this.roomId);
    if (saved) {
      this.userName = saved;
      this.userRole = sessionStorage.getItem('role_' + this.roomId) || 'user';
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

  // ── Connection ───────────────────────────────────────────────────────────

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
    this.userRole = this.isCreator ? 'user' : (roleInput ? roleInput.value : 'user');
    sessionStorage.setItem('name_' + this.roomId, name);
    sessionStorage.setItem('role_' + this.roomId, this.userRole);
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
        alert('This room no longer exists. You will be redirected to the home page.');
        window.location.href = '/';
        return;
      }
      if (event.code === 4005) {
        self.shouldReconnect = false;
        alert('You have been removed from the room by the admin.');
        window.location.href = '/';
        return;
      }
      self.setStatus('disconnected', 'Disconnected – reconnecting…');
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

  // ── Rendering ────────────────────────────────────────────────────────────

  render(state) {
    if (state.users[this.userName]) {
      this.userRole = state.users[this.userName].role;
    }
    if (!state.revealed && state.users[this.userName] && state.users[this.userName].vote === null) {
      this.myVote = null;
    }
    this.renderBacklog(state);
    this.renderParticipants(state);
    this.renderProgress(state);
    this.renderControls(state);
    this.renderResults(state);
    this.syncStory(state);
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

  renderParticipants(state) {
    var self = this;
    var container = document.getElementById('participants');
    container.innerHTML = '';

    var entries = Object.entries(state.users);
    if (entries.length === 0) {
      var msg = document.createElement('p');
      msg.className = 'empty-state';
      msg.textContent = 'No participants yet';
      container.appendChild(msg);
      return;
    }

    var isAdmin = (this.userRole === 'admin');

    entries.forEach(function (entry) {
      var name = entry[0];
      var info = entry[1];
      var voteVal = info.vote;
      var role = info.role;
      var isViewer = (role === 'viewer');

      var card = document.createElement('div');
      card.className = 'participant-card';

      var badge = document.createElement('div');
      if (isViewer) {
        badge.className = 'p-badge viewer-badge';
        badge.textContent = '👁';
      } else if (state.revealed) {
        var isNA = voteVal === null || voteVal === undefined;
        badge.className = 'p-badge revealed' + (isNA ? ' no-vote' : '');
        badge.textContent = isNA ? '–' : voteVal;
      } else {
        badge.className = 'p-badge ' + (voteVal === 'voted' ? 'voted' : 'waiting');
        badge.textContent = voteVal === 'voted' ? '✓' : '…';
      }

      var nameEl = document.createElement('div');
      nameEl.className = 'p-name' + (name === self.userName ? ' me' : '');

      var roleIcon = role === 'admin' ? ' 👑' : '';
      nameEl.textContent = name + roleIcon;

      card.appendChild(badge);
      card.appendChild(nameEl);

      if (isAdmin && name !== self.userName) {
        var actions = document.createElement('div');
        actions.className = 'p-actions';

        var renameBtn = document.createElement('button');
        renameBtn.className = 'btn-icon';
        renameBtn.title = 'Rename';
        renameBtn.textContent = '✏️';
        renameBtn.addEventListener('click', function () { self.renameUser(name); });

        var kickBtn = document.createElement('button');
        kickBtn.className = 'btn-icon btn-icon-danger';
        kickBtn.title = 'Kick';
        kickBtn.textContent = '✕';
        kickBtn.addEventListener('click', function () { self.kickUser(name); });

        actions.appendChild(renameBtn);
        actions.appendChild(kickBtn);
        card.appendChild(actions);
      }

      container.appendChild(card);
    });
  }

  renderProgress(state) {
    if (state.revealed) {
      document.getElementById('vote-progress').textContent = '';
      return;
    }
    var voters = Object.values(state.users).filter(function (info) { return info.role !== 'viewer'; });
    var voted = voters.filter(function (info) { return info.vote === 'voted'; }).length;
    var total = voters.length;
    document.getElementById('vote-progress').textContent =
      total > 0 ? voted + ' of ' + total + ' voted' : '';
  }

  renderControls(state) {
    var cardsPanel = document.getElementById('cards-panel');
    var revealBtn  = document.getElementById('reveal-btn');
    var resetBtn   = document.getElementById('reset-btn');
    var storyBtn   = document.getElementById('story-btn');
    var storyText  = document.getElementById('story-text');

    var isViewer = (this.userRole === 'viewer');
    var canAct   = !isViewer;

    storyText.readOnly = isViewer;
    storyBtn.classList.toggle('hidden', isViewer);

    if (state.revealed) {
      cardsPanel.classList.add('hidden');
      revealBtn.classList.add('hidden');
      resetBtn.classList.toggle('hidden', !canAct);
    } else {
      cardsPanel.classList.toggle('hidden', isViewer);
      revealBtn.classList.toggle('hidden', !canAct);
      resetBtn.classList.add('hidden');

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
      .filter(function (info) {
        return info.role !== 'viewer' && info.vote !== null && info.vote !== undefined && !isNaN(Number(info.vote));
      })
      .map(function (info) { return Number(info.vote); });

    if (numeric.length > 0) {
      var sum = numeric.reduce(function (a, b) { return a + b; }, 0);
      var avg = sum / numeric.length;
      document.getElementById('res-avg').textContent =
        Number.isInteger(avg) ? avg : avg.toFixed(1);
      document.getElementById('res-min').textContent = Math.min.apply(null, numeric);
      document.getElementById('res-max').textContent = Math.max.apply(null, numeric);
    } else {
      ['res-avg', 'res-min', 'res-max'].forEach(function (id) {
        document.getElementById(id).textContent = '–';
      });
    }
  }

  renderBacklog(state) {
    var self = this;
    this.lastState = state;
    var list  = document.getElementById('backlog-list');
    var addRow = document.getElementById('backlog-add-row');
    var emptyMsg = document.getElementById('backlog-empty');
    var backlog = state.backlog || [];
    var isAdmin = (this.userRole === 'admin');

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
      li.className = 'backlog-item' +
        (isActive ? ' active' : '') +
        (isDone   ? ' done'   : '');

      var num = document.createElement('span');
      num.className = 'bli-num';
      num.textContent = (idx + 1) + '.';

      var title = document.createElement('span');
      title.className = 'bli-title';
      title.textContent = item.title;

      li.appendChild(num);
      li.appendChild(title);

      if (isActive) {
        var tag = document.createElement('span');
        tag.className = 'bli-tag active-tag';
        tag.textContent = '▶ Voting';
        li.appendChild(tag);

        if (isAdmin) {
          var doneBtn = document.createElement('button');
          doneBtn.className = 'btn btn-secondary bli-vote-btn';
          doneBtn.textContent = '✓ Mark Done';
          (function (i) {
            doneBtn.onclick = function () { self.markBliDone(i); };
          }(idx));
          li.appendChild(doneBtn);
        }
      } else if (isDone) {
        var tag = document.createElement('span');
        tag.className = 'bli-tag done-tag';
        tag.textContent = '✓ Done';
        li.appendChild(tag);
      } else if (isAdmin) {
        var voteBtn = document.createElement('button');
        voteBtn.className = 'btn btn-secondary bli-vote-btn';
        voteBtn.textContent = 'Vote on this';
        (function (i) {
          voteBtn.onclick = function () { self.selectBli(i); };
        }(idx));
        li.appendChild(voteBtn);
      }

      if (isAdmin) {
        var actions = document.createElement('span');
        actions.className = 'bli-actions';

        var editBtn = document.createElement('button');
        editBtn.className = 'btn-icon';
        editBtn.title = 'Edit';
        editBtn.textContent = '✏️';
        (function (i) {
          editBtn.onclick = function () { self.startEditBli(i); };
        }(idx));

        var delBtn = document.createElement('button');
        delBtn.className = 'btn-icon btn-icon-danger';
        delBtn.title = 'Delete';
        delBtn.textContent = '🗑';
        (function (i) {
          delBtn.onclick = function () { self.confirmDeleteBli(i); };
        }(idx));

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
        (function (i) {
          yesBtn.onclick = function () { self.deleteBli(i); };
        }(idx));

        var noBtn = document.createElement('button');
        noBtn.className = 'btn btn-secondary bli-edit-cancel';
        noBtn.textContent = 'No';
        noBtn.onclick = function () { self.cancelDeleteBli(); };

        confirmRow.appendChild(confirmLabel);
        confirmRow.appendChild(yesBtn);
        confirmRow.appendChild(noBtn);
        li.appendChild(confirmRow);
      }

      // If this item is being edited inline, show input instead of title
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

        var cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-secondary bli-edit-cancel';
        cancelBtn.textContent = '✕';

        (function (i, inp) {
          saveBtn.onclick = function () { self.submitEditBli(i, inp.value); };
          cancelBtn.onclick = function () { self.cancelEditBli(); };
          editInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); self.submitEditBli(i, inp.value); }
            if (e.key === 'Escape') { self.cancelEditBli(); }
          });
        }(idx, editInput));

        editRow.appendChild(editInput);
        editRow.appendChild(saveBtn);
        editRow.appendChild(cancelBtn);
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

  // ── Actions ──────────────────────────────────────────────────────────────

  vote(value) {
    this.myVote = value;
    this.send({ action: 'vote', value: value });
    document.querySelectorAll('.vote-card').forEach(function (card) {
      card.classList.toggle('selected', card.dataset.value === value);
    });
  }

  revealVotes() {
    this.send({ action: 'reveal' });
  }

  newRound() {
    this.myVote = null;
    var story = document.getElementById('story-text').value;
    this.send({ action: 'reset', story: story });
  }

  kickUser(target) {
    this.send({ action: 'kick', target: target });
  }

  renameUser(target) {
    var newName = prompt('Enter new name for "' + target + '":');
    if (!newName) return;
    newName = newName.trim();
    if (!newName) return;
    this.send({ action: 'rename_user', target: target, new_name: newName });
  }

  setStory(btn) {
    var story = document.getElementById('story-text').value;
    this.send({ action: 'set_story', story: story });

    if (!btn) return;
    if (btn._flashTimer) {
      clearTimeout(btn._flashTimer);
    } else {
      btn._origHTML = btn.innerHTML;
    }
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
      if (btn._flashTimer) {
        clearTimeout(btn._flashTimer);
      } else {
        btn._origHTML = btn.innerHTML;
      }
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

  // ── Backlog actions ──────────────────────────────────────────────────────

  selectBli(index) {
    this.send({ action: 'select_bli', index: index });
  }

  markBliDone(index) {
    this.send({ action: 'mark_bli_done', index: index });
  }

  addBliInRoom() {
    var input = document.getElementById('bli-room-input');
    var title = input.value.trim();
    if (!title) return;
    this.send({ action: 'add_bli', title: title });
    input.value = '';
    input.focus();
  }

  startEditBli(index) {
    this.confirmingDeleteBli = null;
    this.editingBliIndex = index;
    this.renderBacklogInline();
  }

  submitEditBli(index, value) {
    var title = value.trim();
    if (!title) return;
    this.editingBliIndex = null;
    this.send({ action: 'edit_bli', index: index, title: title });
  }

  cancelEditBli() {
    this.editingBliIndex = null;
    this.renderBacklogInline();
  }

  confirmDeleteBli(index) {
    this.editingBliIndex = null;
    this.confirmingDeleteBli = index;
    this.renderBacklogInline();
  }

  cancelDeleteBli() {
    this.confirmingDeleteBli = null;
    this.renderBacklogInline();
  }

  deleteBli(index) {
    this.confirmingDeleteBli = null;
    this.send({ action: 'delete_bli', index: index });
  }
}
