/* slideshow.js
   Handles arrow navigation, thumbnail clicks, and video pause on slide change.
   Works with the markup produced by _layouts/post.html.
   Multiple slideshows per page are supported (though unlikely). */

(function () {
  'use strict';

  function initSlideshow(root) {
    const slides     = Array.from(root.querySelectorAll('.slideshow-slide'));
    const thumbs     = Array.from(root.querySelectorAll('.slideshow-thumb'));
    const annotations = Array.from(root.querySelectorAll('.annotation-text'));
    const prevBtn    = root.querySelector('.slideshow-arrow.prev');
    const nextBtn    = root.querySelector('.slideshow-arrow.next');
    const counter    = root.querySelector('.current-slide');

    if (!slides.length) return;

    let current = 0;

    function goTo(index) {
      if (index < 0 || index >= slides.length) return;

      // Pause any playing video on the outgoing slide
      const outVideo = slides[current].querySelector('video');
      if (outVideo) {
        outVideo.pause();
      }

      // Deactivate current
      slides[current].classList.remove('active');
      thumbs[current].classList.remove('active');
      if (annotations[current]) annotations[current].classList.remove('active');

      current = index;

      // Activate new
      slides[current].classList.add('active');
      thumbs[current].classList.add('active');
      if (annotations[current]) annotations[current].classList.add('active');

      // Update counter
      if (counter) counter.textContent = current + 1;

      // Update arrow states
      prevBtn.disabled = current === 0;
      nextBtn.disabled = current === slides.length - 1;
    }

    // Arrow buttons
    prevBtn.addEventListener('click', () => goTo(current - 1));
    nextBtn.addEventListener('click', () => goTo(current + 1));

    // Keyboard navigation (only when focus is within the slideshow)
    root.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft')  goTo(current - 1);
      if (e.key === 'ArrowRight') goTo(current + 1);
    });

    // Thumbnail clicks — always just navigate to that slide
    thumbs.forEach((thumb, i) => {
      thumb.addEventListener('click', () => {
        goTo(i);
      });
    });

    // Initialise arrow states
    prevBtn.disabled = true;
    nextBtn.disabled = slides.length === 1;

    // Make the slideshow focusable for keyboard nav
    root.setAttribute('tabindex', '0');
  }

  document.querySelectorAll('.slideshow').forEach(initSlideshow);
})();