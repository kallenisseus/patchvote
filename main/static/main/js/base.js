document.addEventListener("DOMContentLoaded", () => {
  const passwordInput = document.querySelector("#id_password1");
  const hints = document.querySelector("#password-hints");

  if (!passwordInput || !hints) return;

  const rules = {
    length: (v) => v.length >= 8,
    numeric: (v) => !/^\d+$/.test(v),
    common: (v) => v.length > 0, // real check is server-side
  };

  passwordInput.addEventListener("input", () => {
    const value = passwordInput.value;

    hints.style.display = value.length ? "block" : "none";

    hints.querySelectorAll("li").forEach((li) => {
      const rule = li.dataset.rule;
      if (rules[rule](value)) {
        li.classList.add("success");
        li.classList.remove("danger");
      } else {
        li.classList.add("danger");
        li.classList.remove("success");
      }
    });
  });
});
