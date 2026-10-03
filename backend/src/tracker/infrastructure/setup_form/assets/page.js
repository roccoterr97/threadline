// The set-up page: shows what the wizard says, asks its questions, sends the answers.
// It talks only to the server that served it, and sends the key from the address's
// fragment with every request, so no other page can read or answer the set-up.

(function () {
  'use strict';

  var KEY_HEADER = 'X-Setup-Key';
  var POLL_MILLISECONDS = 1000;
  var key = window.location.hash.slice(1);

  var transcript = document.getElementById('transcript');
  var questionBox = document.getElementById('question');
  var prompt = document.getElementById('prompt');
  var form = document.getElementById('answer-form');
  var input = document.getElementById('answer-input');
  var hint = document.getElementById('hint');
  var primary = document.getElementById('primary');
  var secondary = document.getElementById('secondary');
  var waiting = document.getElementById('waiting');
  var ending = document.getElementById('ending');
  var endingMessage = document.getElementById('ending-message');
  var stop = document.getElementById('stop');

  var next = 0;
  var shownQuestionId = null;
  var finished = false;

  function request(method, path, body) {
    var options = { method: method, headers: {} };
    options.headers[KEY_HEADER] = key;
    if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (response) {
      if (!response.ok) {
        throw new Error('The set-up server answered ' + response.status);
      }
      return response.json();
    });
  }

  function addEntry(entry) {
    var element;
    if (entry.kind === 'link') {
      element = document.createElement('p');
      element.className = 'link';
      var anchor = document.createElement('a');
      anchor.href = entry.text;
      anchor.target = '_blank';
      anchor.rel = 'noreferrer noopener';
      anchor.textContent = 'Open ' + entry.text;
      element.appendChild(anchor);
    } else if (entry.kind === 'answer') {
      element = document.createElement('p');
      element.className = 'answer';
      element.textContent = entry.text + ' ';
      var strong = document.createElement('strong');
      strong.textContent = entry.detail;
      element.appendChild(strong);
    } else {
      element = document.createElement('p');
      element.className = 'said';
      element.textContent = entry.text;
    }
    transcript.appendChild(element);
  }

  function showQuestion(question) {
    if (question === null) {
      questionBox.hidden = true;
      waiting.hidden = finished;
      shownQuestionId = null;
      return;
    }
    if (question.id === shownQuestionId) {
      return;
    }
    shownQuestionId = question.id;
    prompt.textContent = question.prompt;
    waiting.hidden = true;
    questionBox.hidden = false;
    input.hidden = question.kind === 'confirm' || question.kind === 'continue';
    hint.hidden = question.kind !== 'secret';
    input.type = question.kind === 'secret' ? 'password' : 'text';
    input.value = question.kind === 'text' && question.default ? question.default : '';
    secondary.hidden = question.kind !== 'confirm';
    if (question.kind === 'confirm') {
      var yesFirst = question.default !== 'no';
      primary.textContent = yesFirst ? 'Yes' : 'No';
      secondary.textContent = yesFirst ? 'No' : 'Yes';
    } else {
      primary.textContent = 'Continue';
    }
    if (!input.hidden) {
      input.focus();
      if (input.value) {
        input.select();
      }
    } else {
      primary.focus();
    }
    questionBox.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }

  function showEnding(outcome) {
    finished = true;
    questionBox.hidden = true;
    waiting.hidden = true;
    stop.hidden = true;
    ending.hidden = false;
    ending.classList.add(outcome.ok ? 'ok' : 'stopped');
    endingMessage.textContent = outcome.message;
    ending.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }

  function send(value) {
    var id = shownQuestionId;
    if (id === null) {
      return;
    }
    questionBox.hidden = true;
    waiting.hidden = false;
    shownQuestionId = null;
    input.value = '';
    request('POST', '/api/answer', { id: id, value: value }).then(pollNow, pollNow);
  }

  function answerFor(button) {
    var kind = input.hidden ? (secondary.hidden ? 'continue' : 'confirm') : 'text';
    if (kind === 'confirm') {
      return button.textContent === 'Yes' ? 'yes' : 'no';
    }
    if (kind === 'continue') {
      return '';
    }
    return input.value;
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    send(answerFor(primary));
  });

  secondary.addEventListener('click', function () {
    send(answerFor(secondary));
  });

  stop.addEventListener('click', function () {
    stop.disabled = true;
    request('POST', '/api/stop').then(pollNow, pollNow);
  });

  var polling = false;
  var timer = null;

  // One timer only, so answering never starts a second polling loop.
  function schedule(delay) {
    window.clearTimeout(timer);
    timer = window.setTimeout(poll, delay);
  }

  function pollNow() {
    schedule(0);
  }

  function poll() {
    if (finished) {
      return;
    }
    if (polling) {
      schedule(POLL_MILLISECONDS);
      return;
    }
    polling = true;
    request('GET', '/api/state?after=' + next)
      .then(function (state) {
        state.entries.forEach(addEntry);
        next = state.next;
        if (state.finished !== null) {
          showEnding(state.finished);
          return;
        }
        showQuestion(state.question);
      })
      .catch(function () {
        showEnding({ ok: false, message: 'The set-up has ended where it was started.' });
      })
      .then(function () {
        polling = false;
        if (!finished) {
          schedule(POLL_MILLISECONDS);
        }
      });
  }

  pollNow();
})();
