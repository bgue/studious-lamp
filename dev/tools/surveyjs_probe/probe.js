// Builds a survey from a small format-2-shaped JSON and renders it into #host. No inline code.
window.probe = { violations: [], completed: null, errors: [] };
document.addEventListener("securitypolicyviolation", function (e) {
  window.probe.violations.push(e.violatedDirective + " " + e.blockedURI);
});
window.addEventListener("error", function (e) {
  window.probe.errors.push(String(e.message));
});
var json = {
  pages: [{ name: "p1", elements: [
    { type: "text", name: "site", title: "Site" },
    { type: "radiogroup", name: "ok", title: "All clear?", choices: ["yes", "no"] },
    { type: "text", inputType: "number", name: "count", title: "How many?", visibleIf: "{ok} = 'no'" },
  ] }],
};
var survey = new SurveyUI.Model(json);
survey.onComplete.add(function (s) {
  window.probe.completed = JSON.parse(JSON.stringify(s.data));
});
survey.render(document.getElementById("host"));
window.probe.survey = survey;
