/**
 * Exercise Detail — Modern interactions
 * Reading progress bar, scroll reveal animations, floating TOC tracking
 */
(function () {
  'use strict';

  // Keep content visible if this script fails to load. CSS only hides reveal
  // targets after JavaScript has explicitly opted into the animation.
  document.documentElement.classList.add('scroll-reveal-ready');

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- Reading progress bar ---- */
  const progressBar = document.getElementById('reading-progress');
  const docHeight = () => document.documentElement.scrollHeight - window.innerHeight;

  function updateProgress() {
    if (!progressBar) return;
    const availableScroll = docHeight();
    const scrolled = availableScroll > 0 ? window.scrollY / availableScroll : 0;
    progressBar.style.width = Math.min(scrolled * 100, 100) + '%';
  }

  /* ---- Scroll reveal (Intersection Observer) ---- */
  function initScrollReveal() {
    const revealElements = document.querySelectorAll('.scroll-reveal, .scroll-reveal-stagger');
    if (!revealElements.length || prefersReducedMotion || !('IntersectionObserver' in window)) {
      // Fallback: show everything
      revealElements.forEach(function (el) { el.classList.add('visible'); });
      return;
    }

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.08,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(function (el) { observer.observe(el); });

    // Stagger children inside coach-card-grid
    const staggerContainers = document.querySelectorAll('.coach-card-grid, .quality-grid, .numbered-steps');
    staggerContainers.forEach(function (container) {
      const children = container.querySelectorAll('.scroll-reveal-stagger');
      children.forEach(function (child, i) {
        child.style.transitionDelay = (i * 0.08) + 's';
      });
    });
  }

  /* ---- Floating TOC active tracking ---- */
  function initTocTracking() {
    const tocLinks = document.querySelectorAll('.toc-link');
    const tocPills = document.querySelectorAll('.toc-pill');
    const sections = [];

    // Collect section elements
    tocLinks.forEach(function (link) {
      var id = link.getAttribute('data-section');
      var target = document.getElementById(id);
      if (target) sections.push({ id: id, el: target });
    });

    if (!sections.length || !('IntersectionObserver' in window)) return;

    var activeId = sections[0].id;

    function setActive(id) {
      if (id === activeId) return;
      activeId = id;
      tocLinks.forEach(function (l) {
        l.classList.toggle('active', l.getAttribute('data-section') === id);
      });
      tocPills.forEach(function (p) {
        p.classList.toggle('active', p.getAttribute('data-section') === id);
      });
    }

    var tocObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          setActive(entry.target.id);
        }
      });
    }, {
      threshold: 0,
      rootMargin: '-20% 0px -60% 0px'
    });

    sections.forEach(function (s) { tocObserver.observe(s.el); });
  }

  /* ---- Smooth scroll for TOC links ---- */
  function initSmoothScroll() {
    var links = document.querySelectorAll('.toc-link, .toc-pill');
    links.forEach(function (link) {
      link.addEventListener('click', function (e) {
        var href = link.getAttribute('href');
        if (href && href.startsWith('#')) {
          e.preventDefault();
          var target = document.getElementById(href.substring(1));
          if (target) {
            var offset = 80; // account for fixed navbar
            var top = target.getBoundingClientRect().top + window.scrollY - offset;
            window.scrollTo({
              top: top,
              behavior: prefersReducedMotion ? 'auto' : 'smooth'
            });
          }
        }
      });
    });
  }

  /* ---- Init ---- */
  document.addEventListener('DOMContentLoaded', function () {
    updateProgress();
    initScrollReveal();
    initTocTracking();
    initSmoothScroll();
  });

  window.addEventListener('scroll', updateProgress, { passive: true });
  window.addEventListener('resize', updateProgress, { passive: true });
})();
