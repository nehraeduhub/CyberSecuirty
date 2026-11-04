/* NimbuPay phishing-awareness SIMULATION — Tech Guardians
 *
 * SAFETY GUARANTEES (by design):
 *  - No fetch/XHR/WebSocket/form action: nothing leaves the browser.
 *  - No localStorage/sessionStorage/cookies: nothing is persisted.
 *  - Field values are read only to prove "we COULD have captured this",
 *    masked, then discarded when the page resets.
 */
(function () {
  "use strict";

  var fake   = document.getElementById("fake");
  var reveal = document.getElementById("reveal");
  var form   = document.getElementById("loginForm");
  var echo   = document.getElementById("echo");
  var again  = document.getElementById("again");

  function showReveal(e) {
    if (e) e.preventDefault();      // never submit anywhere

    // Read values ONLY to demonstrate capture, then mask. Not stored, not sent.
    var user = (document.getElementById("user").value || "").trim();
    var pass = (document.getElementById("pass").value || "");

    var maskedUser = user ? user.charAt(0) + "•••" : "(nothing typed)";
    var maskedPass = pass ? "•".repeat(Math.min(pass.length, 12)) : "(nothing typed)";

    echo.textContent =
      "In a real attack, the criminal would now have — username: " +
      maskedUser + "   password: " + maskedPass +
      "   (shown masked here; this demo did NOT send or save it).";

    // Discard the values immediately.
    user = null; pass = null;
    form.reset();

    fake.classList.add("hidden");
    reveal.classList.remove("hidden");
    window.scrollTo(0, 0);
  }

  function resetDemo() {
    echo.textContent = "";
    reveal.classList.add("hidden");
    fake.classList.remove("hidden");
  }

  form.addEventListener("submit", showReveal);
  again.addEventListener("click", resetDemo);

  // Extra guarantee: block any accidental navigation from the form.
  form.setAttribute("action", "javascript:void(0)");
})();
