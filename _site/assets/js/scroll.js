document.addEventListener("DOMContentLoaded", () => {
  const bg = document.querySelector(".tank-background");

  window.addEventListener("scroll", () => {
    const scrollY = window.scrollY;

    // Move background slower than page scroll
    bg.style.transform = `translateY(${scrollY * 0.3}px)`;
  });
});