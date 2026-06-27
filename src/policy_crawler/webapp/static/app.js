// Inbox interactivity: delete confirmations + checkbox bulk actions.
// Progressive enhancement — every action also works as a plain form POST.
(function () {
  "use strict";

  // ── Confirmation gates ───────────────────────────────────────────────
  document.querySelectorAll("form.js-confirm").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm("Delete this job? It will be removed from your views.")) {
        e.preventDefault();
      }
    });
  });
  document.querySelectorAll("form.js-confirm-all").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm("Delete ALL archived jobs? This cannot be undone from the app.")) {
        e.preventDefault();
      }
    });
  });

  // ── Bulk selection ───────────────────────────────────────────────────
  var checks = Array.prototype.slice.call(document.querySelectorAll(".job-check"));
  if (!checks.length) return;

  var selectAll = document.getElementById("select-all");
  var bulkActions = document.getElementById("bulk-actions");
  var bulkCount = document.getElementById("bulk-count");
  var csrf = (document.getElementById("csrf-token") || {}).value || "";
  var view = (document.getElementById("current-view") || {}).value || "inbox";

  function selectedIds() {
    return checks.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
  }

  function refresh() {
    var ids = selectedIds();
    if (bulkActions) bulkActions.hidden = ids.length === 0;
    if (bulkCount) bulkCount.textContent = ids.length + " selected";
    if (selectAll) selectAll.checked = ids.length === checks.length && checks.length > 0;
  }

  checks.forEach(function (c) { c.addEventListener("change", refresh); });

  if (selectAll) {
    selectAll.addEventListener("change", function () {
      checks.forEach(function (c) { c.checked = selectAll.checked; });
      refresh();
    });
  }

  document.querySelectorAll(".bulk-op").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var ids = selectedIds();
      if (!ids.length) return;
      var op = btn.getAttribute("data-op");
      if (op === "delete" &&
          !window.confirm("Delete " + ids.length + " selected job(s)?")) {
        return;
      }
      var form = document.createElement("form");
      form.method = "post";
      form.action = "/inbox/action";
      function hidden(name, value) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        form.appendChild(input);
      }
      hidden("csrf_token", csrf);
      hidden("op", op);
      hidden("view", view);
      ids.forEach(function (id) { hidden("job_ids", id); });
      document.body.appendChild(form);
      form.submit();
    });
  });

  refresh();
})();
