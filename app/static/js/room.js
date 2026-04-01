let userName = null;
let userRole = 'user';
let ws = null;
let myVote = null;
let shouldReconnect = true;
let editingBliIndex = null;
let lastState = null;
let confirmingDeleteBli = null;

window.addEventListener('DOMContentLoaded', function () {
  document.getElementById('room-id-text').textContent = ROOM_ID;

  if (IS_CREATOR) {
    var roleSelector = document.getElementById('role-selector');
    if (roleSelector) roleSelector.style.display = 'none';
  }

  var nameInput = document.getElementById('name-input');
  nameInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') submitName();
  });
  nameInput.addEventListener('input', function () {
    nameInput.classList.remove('error');
  });

  document.getElementById('story-text').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      setStory(document.getElementById('story-btn'));
    }
  });

  document.getElementById('bli-room-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addBliInRoom();
    }
  });

  renderCards();

  var saved = sessionStorage.getItem('name_' + ROOM_ID);
  if (saved) {
    userName = saved;
    userRole = sessionStorage.getItem('role_' + ROOM_ID) || 'user';
    document.getElementById('name-modal').classList.add('hidden');
    showApp();
    connect();
  } else {
    setTimeout(function () { nameInput.focus(); }, 50);
  }
});

window.addEventListener('beforeunload', function () {
  shouldReconnect = false;
  if (ws) ws.close();
});

function submitName() {
  var input = document.getElementById('name-input');
  var name = input.value.trim();
  if (!name) {
    input.classList.add('error');
    input.focus();
    return;
  }
  var roleInput = document.querySelector('input[name="role"]:checked');
  userName = name;
  userRole = IS_CREATOR ? 'user' : (roleInput ? roleInput.value : 'user');
  sessionStorage.setItem('name_' + ROOM_ID, name);
  sessionStorage.setItem('role_' + ROOM_ID, userRole);
  document.getElementById('name-modal').classList.add('hidden');
  showApp();
  connect();
}

function showApp() {
  document.getElementById('app').classList.remove('hidden');
}

function connect() {
  var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var url = protocol + '//' + location.host + '/ws/' + ROOM_ID + '/' + encodeURIComponent(userName) + '?role=' + encodeURIComponent(userRole);
  ws = new WebSocket(url);

  ws.onopen = function () {
    setStatus('connected', 'Connected');
  };

  ws.onmessage = function (event) {
    var state = JSON.parse(event.data);
    if (state.renamed && state.renamed.from === userName) {
      userName = state.renamed.to;
      sessionStorage.setItem('name_' + ROOM_ID, userName);
    }
    render(state);
  };

  ws.onerror = function () {
    setStatus('disconnected', 'Connection error');
  };

  ws.onclose = function (event) {
    if (event.code === 4004) {
      shouldReconnect = false;
      alert('This room no longer exists. You will be redirected to the home page.');
      window.location.href = '/';
      return;
    }
    if (event.code === 4005) {
      shouldReconnect = false;
      alert('You have been removed from the room by the admin.');
      window.location.href = '/';
      return;
    }
    setStatus('disconnected', 'Disconnected – reconnecting…');
    if (shouldReconnect) setTimeout(connect, 2500);
  };
}

function setStatus(cls, text) {
  var el = document.getElementById('conn-status');
  el.className = 'status-badge ' + cls;
  el.textContent = text;
}

function render(state) {
  if (state.users[userName]) {
    userRole = state.users[userName].role;
  }
  if (!state.revealed && state.users[userName] && state.users[userName].vote === null) {
    myVote = null;
  }
  renderBacklog(state);
  renderParticipants(state);
  renderProgress(state);
  renderControls(state);
  renderResults(state);
  syncStory(state);
}

function renderCards() {
  var grid = document.getElementById('cards-grid');
  CARDS.forEach(function (value) {
    var btn = document.createElement('button');
    btn.className = 'vote-card';
    btn.dataset.value = value;
    btn.textContent = value;
    btn.addEventListener('click', function () { vote(value); });
    grid.appendChild(btn);
  });
}

function renderParticipants(state) {
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

  var isAdmin = (userRole === 'admin');

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
    nameEl.className = 'p-name' + (name === userName ? ' me' : '');

    var roleIcon = role === 'admin' ? ' 👑' : '';
    nameEl.textContent = name + roleIcon;

    card.appendChild(badge);
    card.appendChild(nameEl);

    if (isAdmin && name !== userName) {
      var actions = document.createElement('div');
      actions.className = 'p-actions';

      var renameBtn = document.createElement('button');
      renameBtn.className = 'btn-icon';
      renameBtn.title = 'Rename';
      renameBtn.textContent = '✏️';
      renameBtn.addEventListener('click', function () { renameUser(name); });

      var kickBtn = document.createElement('button');
      kickBtn.className = 'btn-icon btn-icon-danger';
      kickBtn.title = 'Kick';
      kickBtn.textContent = '✕';
      kickBtn.addEventListener('click', function () { kickUser(name); });

      actions.appendChild(renameBtn);
      actions.appendChild(kickBtn);
      card.appendChild(actions);
    }

    container.appendChild(card);
  });
}

function renderProgress(state) {
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

function renderControls(state) {
  var cardsPanel = document.getElementById('cards-panel');
  var revealBtn  = document.getElementById('reveal-btn');
  var resetBtn   = document.getElementById('reset-btn');
  var storyBtn   = document.getElementById('story-btn');
  var storyText  = document.getElementById('story-text');

  var isAdmin  = (userRole === 'admin');
  var isViewer = (userRole === 'viewer');
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
      document.querySelectorAll('.vote-card').forEach(function (card) {
        card.classList.toggle('selected', card.dataset.value === myVote);
      });
    }
  }
}

function renderResults(state) {
  var panel = document.getElementById('results-panel');
  if (!state.revealed) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');

  var numeric = Object.values(state.users)
    .filter(function (info) {
      return info.role !== 'viewer' && info.vote !== null && info.vote !== undefined && !isNaN(parseFloat(info.vote));
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

function renderBacklog(state) {
  lastState = state;
  var panel = document.getElementById('backlog-panel');
  var list  = document.getElementById('backlog-list');
  var addRow = document.getElementById('backlog-add-row');
  var emptyMsg = document.getElementById('backlog-empty');
  var backlog = state.backlog || [];
  var isAdmin = (userRole === 'admin');

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
          doneBtn.onclick = function () { markBliDone(i); };
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
        voteBtn.onclick = function () { selectBli(i); };
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
        editBtn.onclick = function () { startEditBli(i); };
      }(idx));

      var delBtn = document.createElement('button');
      delBtn.className = 'btn-icon btn-icon-danger';
      delBtn.title = 'Delete';
      delBtn.textContent = '🗑';
      (function (i) {
        delBtn.onclick = function () { confirmDeleteBli(i); };
      }(idx));

      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      li.appendChild(actions);
    }

    // Inline delete confirmation
    if (isAdmin && confirmingDeleteBli === idx) {
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
        yesBtn.onclick = function () { deleteBli(i); };
      }(idx));

      var noBtn = document.createElement('button');
      noBtn.className = 'btn btn-secondary bli-edit-cancel';
      noBtn.textContent = 'No';
      noBtn.onclick = function () { cancelDeleteBli(); };

      confirmRow.appendChild(confirmLabel);
      confirmRow.appendChild(yesBtn);
      confirmRow.appendChild(noBtn);
      li.appendChild(confirmRow);
    }

    // If this item is being edited inline, show input instead of title
    if (isAdmin && editingBliIndex === idx) {
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
        saveBtn.onclick = function () { submitEditBli(i, inp.value); };
        cancelBtn.onclick = function () { cancelEditBli(); };
        editInput.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') { e.preventDefault(); submitEditBli(i, inp.value); }
          if (e.key === 'Escape') { cancelEditBli(); }
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

function renderBacklogInline() {
  if (lastState) renderBacklog(lastState);
}

function selectBli(index) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'select_bli', index: index }));
}

function markBliDone(index) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'mark_bli_done', index: index }));
}

function addBliInRoom() {
  var input = document.getElementById('bli-room-input');
  var title = input.value.trim();
  if (!title) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'add_bli', title: title }));
  input.value = '';
  input.focus();
}

function startEditBli(index) {
  editingBliIndex = index;
  renderBacklogInline();
}

function submitEditBli(index, value) {
  var title = value.trim();
  editingBliIndex = null;
  if (!title) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'edit_bli', index: index, title: title }));
}

function cancelEditBli() {
  editingBliIndex = null;
  renderBacklogInline();
}

function confirmDeleteBli(index) {
  confirmingDeleteBli = index;
  renderBacklogInline();
}

function cancelDeleteBli() {
  confirmingDeleteBli = null;
  renderBacklogInline();
}

function deleteBli(index) {
  confirmingDeleteBli = null;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'delete_bli', index: index }));
}

function syncStory(state) {
  var el = document.getElementById('story-text');
  if (document.activeElement !== el) el.value = state.story || '';
}

function vote(value) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  myVote = value;
  ws.send(JSON.stringify({ action: 'vote', value: value }));
  document.querySelectorAll('.vote-card').forEach(function (card) {
    card.classList.toggle('selected', card.dataset.value === value);
  });
}

function revealVotes() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'reveal' }));
}

function newRound() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  myVote = null;
  var story = document.getElementById('story-text').value;
  ws.send(JSON.stringify({ action: 'reset', story: story }));
}

function kickUser(target) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'kick', target: target }));
}

function renameUser(target) {
  var newName = prompt('Enter new name for "' + target + '":');
  if (!newName) return;
  newName = newName.trim();
  if (!newName) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action: 'rename_user', target: target, new_name: newName }));
}

function setStory(btn) {
  var story = document.getElementById('story-text').value;

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'set_story', story: story }));
  }

  if (!btn) return;
  var orig = btn.innerHTML;
  btn.innerHTML = '✓ Updated';
  btn.classList.add('btn-success-flash');
  setTimeout(function () {
    btn.innerHTML = orig;
    btn.classList.remove('btn-success-flash');
  }, 2000);
}

function copyLink() {
  var btn = document.getElementById('copy-btn');
  var orig = btn.innerHTML;
  var cleanUrl = location.origin + location.pathname;

  function showSuccess() {
    btn.innerHTML = '✓ Copied!';
    btn.classList.add('btn-success-flash');
    setTimeout(function () {
      btn.innerHTML = orig;
      btn.classList.remove('btn-success-flash');
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
