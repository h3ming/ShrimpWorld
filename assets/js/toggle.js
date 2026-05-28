document.addEventListener("DOMContentLoaded", () => {

  const buttons = document.querySelectorAll(".toggle-btn");

  buttons.forEach(button => {

    button.addEventListener("click", () => {

      // find the current post card
      const postCard = button.closest(".post-card");

      // find the hidden full content inside this card
      const fullContent = postCard.querySelector(".post-full");

      // safety check
      if (!fullContent) return;

      // toggle visibility
      fullContent.classList.toggle("hidden");

      // update button text
      if (fullContent.classList.contains("hidden")) {
        button.textContent = "Read more";
      } else {
        button.textContent = "Show less";
      }

    });

  });

});