const CARDS = ['3', '6', '9', '12', '15', '18', '21', '24', '27', '30', '30+','?'];

let userName = null;
let ws = null;
let myVote = null;
let shouldReconnect = true;

window.addEventListener('DOMContentLoaded', function () {
  document.getElementById('room-id-text').textContent = ROOM_ID;

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
      setStory();
    }
  });

  renderCards();

  var saved = sessionStorage.getItem('name_' + ROOM_ID);
  if (saved) {
    userName = saved;
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
  userName = name;
  sessionStorage.setItem('name_' + ROOM_ID, name);
  document.getElementById('name-modal').classList.add('hidden');
  showApp();
  connect();
}

function showApp() {
  document.getElementById('app').classList.remove('hidden');
}

function connect() {
  var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var url = protocol + '//' + location.host + '/ws/' + ROOM_ID + '/' + encodeURIComponent(userName);
  ws = new WebSocket(url);

  ws.onopen = function () {
    setStatus('connected', 'Connected');
  };

  ws.onmessage = function (event) {
    var state = JSON.parse(event.data);
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
  if (!state.revealed && state.users[userName] === null) {
    myVote = null;
  }
  renderParticipants(state);
  renderProgress(state);
  renderControls(state);
  renderResults(state);
  syncStory(state.story);
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

  entries.forEach(function (entry) {
    var name = entry[0];
    var voteVal = entry[1];

    var card = document.createElement('div');
    card.className = 'participant-card';

    var badge = document.createElement('div');
    if (state.revealed) {
      var isNA = voteVal === null || voteVal === undefined;
      badge.className = 'p-badge revealed' + (isNA ? ' no-vote' : '');
      badge.textContent = isNA ? '–' : voteVal;
    } else {
      badge.className = 'p-badge ' + (voteVal === 'voted' ? 'voted' : 'waiting');
      badge.textContent = voteVal === 'voted' ? '✓' : '…';
    }

    var nameEl = document.createElement('div');
    nameEl.className = 'p-name' + (name === userName ? ' me' : '');
    nameEl.textContent = name;

    card.appendChild(badge);
    card.appendChild(nameEl);
    container.appendChild(card);
  });
}

function renderProgress(state) {
  if (state.revealed) {
    document.getElementById('vote-progress').textContent = '';
    return;
  }
  var vals = Object.values(state.users);
  var voted = vals.filter(function (v) { return v === 'voted'; }).length;
  var total = vals.length;
  document.getElementById('vote-progress').textContent =
    total > 0 ? voted + ' of ' + total + ' voted' : '';
}

function renderControls(state) {
  var cardsPanel = document.getElementById('cards-panel');
  var revealBtn  = document.getElementById('reveal-btn');
  var resetBtn   = document.getElementById('reset-btn');

  if (state.revealed) {
    cardsPanel.classList.add('hidden');
    revealBtn.classList.add('hidden');
    resetBtn.classList.remove('hidden');
  } else {
    cardsPanel.classList.remove('hidden');
    revealBtn.classList.remove('hidden');
    resetBtn.classList.add('hidden');

    document.querySelectorAll('.vote-card').forEach(function (card) {
      card.classList.toggle('selected', card.dataset.value === myVote);
    });
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
    .filter(function (v) {
      return v !== null && v !== undefined && !isNaN(parseFloat(v));
    })
    .map(Number);

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

function syncStory(story) {
  var el = document.getElementById('story-text');
  if (document.activeElement !== el) el.value = story || '';
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

function setStory() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  var story = document.getElementById('story-text').value;
  ws.send(JSON.stringify({ action: 'set_story', story: story }));
}

function copyLink() {
  var btn = document.getElementById('copy-btn');
  var orig = btn.innerHTML;

  function showSuccess() {
    btn.innerHTML = '✓ Copied!';
    btn.style.cssText = 'background:#10b981;color:white;border-color:#10b981';
    setTimeout(function () {
      btn.innerHTML = orig;
      btn.style.cssText = '';
    }, 2000);
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(location.href).then(showSuccess);
  } else {
    var ta = document.createElement('textarea');
    ta.value = location.href;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showSuccess();
  }
}
