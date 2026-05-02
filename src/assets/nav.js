// OpenCast nav.js — minimal JS for the shared navigation
(function () {
  'use strict';

  // Mark the current page link as active based on the filename
  var nav = document.getElementById('main-nav');
  if (!nav) return;

  var current = window.location.pathname.split('/').pop() || 'index.html';
  var links = nav.querySelectorAll('a');
  links.forEach(function (link) {
    var href = link.getAttribute('href') || '';
    if (href === current) {
      link.classList.add('active');
    }
  });
})();
