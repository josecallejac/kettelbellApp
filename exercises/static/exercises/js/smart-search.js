/**
 * KettleBell Pro - Smart Search
 *
 * Autocomplete suggestions and debounced search input.
 */

(function () {
  'use strict';

  var DEBOUNCE_MS = 300;
  var autocompleteTimer = null;

  /* ---- DOM refs ---- */
  var searchInput = document.querySelector('.search-input[name="q"]');
  var searchForm = document.querySelector('.search-form');
  if (!searchInput || !searchForm) return;

  /* ---- Create autocomplete dropdown ---- */
  var dropdown = document.createElement('div');
  dropdown.className = 'autocomplete-dropdown';
  dropdown.style.display = 'none';
  searchInput.parentNode.insertBefore(dropdown, searchInput.nextSibling);

  /* ---- Debounce ---- */
  function debounce(fn, ms) {
    return function () {
      clearTimeout(autocompleteTimer);
      autocompleteTimer = setTimeout(fn, ms);
    };
  }

  /* ---- Fetch autocomplete suggestions ---- */
  function fetchSuggestions(query) {
    if (query.length < 2) {
      dropdown.style.display = 'none';
      return;
    }

    fetch('/api/exercises/autocomplete/?q=' + encodeURIComponent(query))
      .then(function (res) { return res.json(); })
      .then(function (data) {
        renderSuggestions(data.suggestions);
      })
      .catch(function () {
        dropdown.style.display = 'none';
      });
  }

  /* ---- Render autocomplete dropdown ---- */
  function renderSuggestions(suggestions) {
    if (!suggestions.length) {
      dropdown.style.display = 'none';
      return;
    }

    dropdown.innerHTML = suggestions.map(function (s) {
      return '<a href="/exercise/' + s.slug + '/" class="autocomplete-item">' +
        '<span class="autocomplete-name">' + escapeHtml(s.name) + '</span>' +
        '<span class="autocomplete-meta">' +
          '<span class="autocomplete-cat">' + escapeHtml(s.category) + '</span>' +
          '<span class="autocomplete-diff">' + escapeHtml(s.difficulty) + '</span>' +
        '</span>' +
      '</a>';
    }).join('');

    dropdown.style.display = 'block';
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /* ---- Event listeners ---- */
  searchInput.addEventListener('input', debounce(function () {
    fetchSuggestions(searchInput.value.trim());
  }, DEBOUNCE_MS));

  searchInput.addEventListener('focus', function () {
    if (searchInput.value.trim().length >= 2) {
      fetchSuggestions(searchInput.value.trim());
    }
  });

  /* Close dropdown when clicking outside */
  document.addEventListener('click', function (e) {
    if (!dropdown.contains(e.target) && e.target !== searchInput) {
      dropdown.style.display = 'none';
    }
  });

  /* Close dropdown on Escape */
  searchInput.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      dropdown.style.display = 'none';
    }
  });

})();
