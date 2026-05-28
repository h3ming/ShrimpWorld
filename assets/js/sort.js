// document.addEventListener("DOMContentLoaded", () => {
//   const list = document.getElementById("postList");
//   const cards = Array.from(document.querySelectorAll(".post-card"));

//   function render(sorted) {
//     sorted.forEach(card => list.appendChild(card));
//   }

//   document.getElementById("sort-newest").addEventListener("click", () => {
//     const sorted = [...cards].sort((a, b) => b.dataset.date - a.dataset.date);
//     render(sorted);
//   });

//   document.getElementById("sort-oldest").addEventListener("click", () => {
//     const sorted = [...cards].sort((a, b) => a.dataset.date - b.dataset.date);
//     render(sorted);
//   });
// });