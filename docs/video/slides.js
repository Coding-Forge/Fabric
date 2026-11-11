const slides = Array.from(document.querySelectorAll(".slide"));
const previous = document.querySelector("#previous");
const next = document.querySelector("#next");
const notes = document.querySelector("#notes");
const noteToggle = document.querySelector("#toggle-notes");
const announcement = document.querySelector("#announcement");
const counter = document.querySelector("#counter");
const parameters = new URLSearchParams(location.search);
let active = 0;

function showSlide(index) {
  active = Math.max(0, Math.min(slides.length - 1, index));
  slides.forEach((slide, position) => { slide.hidden = position !== active; });
  previous.disabled = active === 0;
  next.disabled = active === slides.length - 1;
  notes.textContent = slides[active].querySelector(".speaker-notes").content.textContent.trim();
  announcement.textContent = `Slide ${active + 1} of ${slides.length}`;
  counter.textContent = `${String(active + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
  history.replaceState(null, "", `${location.pathname}${location.search}#slide-${active + 1}`);
}

previous.addEventListener("click", () => showSlide(active - 1));
next.addEventListener("click", () => showSlide(active + 1));
noteToggle.addEventListener("click", () => {
  notes.hidden = !notes.hidden;
  noteToggle.setAttribute("aria-expanded", String(!notes.hidden));
});
document.addEventListener("keydown", (event) => {
  if (event.target.closest("button, audio, input, textarea, select, a")) return;
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    event.preventDefault();
    showSlide(active + (event.key === "ArrowRight" ? 1 : -1));
  }
});
if (parameters.get("capture") === "1") document.body.classList.add("capture");
const requested = /^#slide-(\d+)$/.exec(location.hash);
showSlide(requested ? Number(requested[1]) - 1 : 0);
