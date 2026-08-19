/**
 * KettleBell Pro - Smart Search
 *
 * Autocomplete suggestions, combined filters (category, difficulty, muscle),
 * and debounced search input.
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

  /* ---- Create filter chips container ---- */
  var filtersContainer = document.createElement('div');
  filtersContainer.className = 'search-filters';
  searchForm.parentNode.insertBefore(filtersContainer, searchForm.nextSibling);

  /* ---- CSRF helper ---- */
  function getCSRF() {
    var cookie = document.cookie.split(';').find(function (c) { return c.trim().startsWith('csrftoken='); });
    return cookie ? cookie.split('=')[1] : '';
  }

  /* ---- Debounce ---- */
  function debounce(fn, ms) {
    return function () {
      clearTimeout(autocompleteTimer);
      autocompleteTimer = setTimeout(fn, ms);
    };
  }

  /* ---- Build URL with current filters ---- */
  function buildFilterUrl(params) {
    var url = new URL(window.location.href.split('?')[0]);
    var current = new URLSearchParams(window.location.search);

    /* Preserve existing params, override with new ones */
    Object.keys(params).forEach(function (key) {
      if (params[key]) {
        url.searchParams.set(key, params[key]);
      } else {
        url.searchParams.delete(key);
      }
    });

    /* Preserve q if present */
    var q = current.get('q');
    if (q && !params.hasOwnProperty('q')) {
      url.searchParams.set('q', q);
    }

    return url.toString();
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

  /* ---- Fetch filter options and render chips ---- */
  function initFilters() {
    fetch('/api/exercises/filters/')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        renderFilterChips(data);
      })
      .catch(function () {});
  }

  function renderFilterChips(data) {
    var urlParams = new URLSearchParams(window.location.search);
    var activeCategory = urlParams.get('category') || '';
    var activeDifficulty = urlParams.get('difficulty') || '';
    var activeMuscle = urlParams.get('muscle') || '';

    var html = '';

    /* Category chips */
    html += '<div class="filter-group">';
    html += '<span class="filter-label">Categoría:</span>';
    html += '<div class="filter-chips">';
    html += '<a href="' + buildFilterUrl({ category: '' }) + '" class="filter-chip' + (!activeCategory ? ' active' : '') + '">Todas</a>';
    data.categories.forEach(function (cat) {
      var isActive = activeCategory === cat[0];
      html += '<a href="' + buildFilterUrl({ category: cat[0] }) + '" class="filter-chip' + (isActive ? ' active' : '') + '">' + escapeHtml(cat[1]) + '</a>';
    });
    html += '</div></div>';

    /* Difficulty chips */
    html += '<div class="filter-group">';
    html += '<span class="filter-label">Nivel:</span>';
    html += '<div class="filter-chips">';
    html += '<a href="' + buildFilterUrl({ difficulty: '' }) + '" class="filter-chip' + (!activeDifficulty ? ' active' : '') + '">Todos</a>';
    data.difficulties.forEach(function (diff) {
      var isActive = activeDifficulty === diff[0];
      html += '<a href="' + buildFilterUrl({ difficulty: diff[0] }) + '" class="filter-chip' + (isActive ? ' active' : '') + '">' + escapeHtml(diff[1]) + '</a>';
    });
    html += '</div></div>';

    /* Muscle chips (top 8) */
    if (data.muscles.length > 0) {
      html += '<div class="filter-group">';
      html += '<span class="filter-label">Músculo:</span>';
      html += '<div class="filter-chips">';
      html += '<a href="' + buildFilterUrl({ muscle: '' }) + '" class="filter-chip' + (!activeMuscle ? ' active' : '') + '">Todos</a>';
      var topMuscles = data.muscles.slice(0, 10);
      topMuscles.forEach(function (m) {
        var isActive = activeMuscle === m;
        html += '<a href="' + buildFilterUrl({ muscle: m }) + '" class="filter-chip' + (isActive ? ' active' : '') + '">' + escapeHtml(m) + '</a>';
      });
      html += '</div></div>';
    }

    filtersContainer.innerHTML = html;
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

  /* ---- Init ---- */
  initFilters();
})();
