// The fill page of /web/forms (V3-F3): builds the SurveyJS model from the JSON block, sends the
// answers. The browser only helps the person; the server validates. No eval, no innerHTML, no
// inline handler; the renderer gets plain text only (no onTextMarkdown handler is ever added).
"use strict";
(function () {
  var form = document.getElementById("fill-form");
  var block = document.getElementById("form-model");
  var host = document.getElementById("survey");
  var answersField = document.getElementById("answers_json");
  var draftField = document.getElementById("draft_id");
  var status = document.getElementById("fill-status");
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (!form || !block || !host || !window.SurveyUI) {
    return;
  }
  var csrf = meta ? meta.getAttribute("content") : "";
  var noted = form.getAttribute("data-format") === "1"; // format 1 answers carry a note key
  var survey = new window.SurveyUI.Model(JSON.parse(block.textContent));
  survey.mode = "edit";
  survey.showCompletedPage = false;

  function say(text, bad) {
    status.textContent = text;
    status.className = bad ? "tl-status tl-fill-bad" : "tl-status";
  }

  function saved() {
    var out = {};
    JSON.parse(answersField.value || "[]").forEach(function (a) {
      out[a.q] = a.value;
    });
    return out;
  }

  function answers() {
    var data = survey.data;
    var out = [];
    Object.keys(data).forEach(function (q) {
      var v = data[q];
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) {
        return;
      }
      var question = survey.getQuestionByName(q);
      if (question && question.inputType === "number" && typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) {
        v = Number(v); // the server takes a number for a number question, not its text
      }
      var entry = { q: q, value: v };
      if (noted) {
        entry.note = null;
      }
      out.push(entry);
    });
    return out;
  }

  function text_of(html) {
    return new DOMParser().parseFromString(html, "text/html").body.textContent.trim();
  }

  function send(url, onDone) {
    answersField.value = JSON.stringify(answers());
    var body = new URLSearchParams();
    body.set("csrf", csrf);
    body.set("draft_id", draftField.value);
    body.set("answers_json", answersField.value);
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    })
      .then(function (response) {
        return response.text().then(function (html) {
          onDone(response, html);
        });
      })
      .catch(function () {
        say("! the form could not be sent; check the connection and try again", true);
      });
  }

  survey.onCompleting.add(function (_sender, options) {
    options.allow = false; // stay on the page until the server has answered
    say("Sending", false);
    send(form.getAttribute("action"), function (response, html) {
      if (response.redirected) {
        window.location.assign(response.url);
      } else {
        say(text_of(html), true);
      }
    });
  });

  var save = document.getElementById("save-draft");
  if (save) {
    save.addEventListener("click", function () {
      send(form.getAttribute("data-draft-url"), function (response, html) {
        var id = response.headers.get("X-Draft-Id");
        if (response.ok && id) {
          draftField.value = id;
          say(text_of(html), false);
        } else {
          say(text_of(html), true);
        }
      });
    });
  }

  survey.data = saved();
  survey.render(host);
})();
