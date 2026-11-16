(() => {
  "use strict";
  document.documentElement.classList.add("js");

  const menu = document.querySelector(".menu-toggle");
  const navigation = document.querySelector("#nav-links");
  if (menu && navigation) {
    menu.hidden = false;
    const closeMenu = () => {
      menu.setAttribute("aria-expanded", "false");
      navigation.classList.remove("is-open");
    };
    menu.addEventListener("click", () => {
      const expanded = menu.getAttribute("aria-expanded") !== "true";
      menu.setAttribute("aria-expanded", String(expanded));
      navigation.classList.toggle("is-open", expanded);
    });
    navigation.addEventListener("click", event => {
      if (event.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && menu.getAttribute("aria-expanded") === "true") {
        closeMenu();
        menu.focus();
      }
    });
  }

  const search = document.querySelector("#resource-search");
  const category = document.querySelector("#resource-category");
  const cards = [...document.querySelectorAll("[data-resource]")];
  if (search && category && cards.length) {
    document.querySelector(".library-tools").hidden = false;
    const count = document.querySelector("#result-count");
    const empty = document.querySelector("#no-results");
    const filter = () => {
      const words = search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      let matches = 0;
      for (const card of cards) {
        const text = `${card.textContent} ${card.dataset.keywords || ""}`.toLowerCase();
        const visible = (category.value === "all" || card.dataset.category === category.value)
          && words.every(word => text.includes(word));
        card.hidden = !visible;
        if (visible) matches++;
      }
      count.textContent = `${matches} ${matches === 1 ? "resource" : "resources"}${matches === cards.length ? " to explore" : ` of ${cards.length}`}`;
      empty.hidden = matches !== 0;
    };
    search.addEventListener("input", filter);
    category.addEventListener("change", filter);
    filter();
  }

  for (const video of document.querySelectorAll("video")) {
    const fallback = video.closest("figure")?.querySelector(".video-error");
    if (fallback) {
      const showFallback = () => { fallback.hidden = false; };
      video.addEventListener("error", showFallback);
      for (const source of video.querySelectorAll("source")) {
        source.addEventListener("error", showFallback);
      }
    }
  }
})();
