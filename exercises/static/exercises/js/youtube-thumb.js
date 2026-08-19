/**
 * KettleBell Pro - YouTube Thumbnail Extractor
 *
 * Extracts YouTube video IDs from URLs and sets thumbnail images.
 * Works with two patterns:
 *   1. Multiple cards: elements with [data-video-url] and img.video-thumb-img inside
 *   2. Single element: img[data-video-url] directly
 */

(function () {
  'use strict';

  var REGEXP = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=|shorts\/)([^#&?]*).*/;
  var FALLBACK = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';

  function extractVideoId(url) {
    if (!url) return null;
    var match = url.match(REGEXP);
    if (match && match[2] && match[2].length === 11) {
      return match[2];
    }
    return null;
  }

  function setThumbnail(img, videoId) {
    img.onerror = function () { img.src = FALLBACK; };
    if (videoId) {
      img.src = 'https://i.ytimg.com/vi/' + videoId + '/hqdefault.jpg';
    } else {
      img.src = FALLBACK;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    /* Pattern 1: cards with data-video-url attribute */
    document.querySelectorAll('[data-video-url]').forEach(function (el) {
      var url = el.dataset.videoUrl;
      var videoId = extractVideoId(url);

      /* If the element itself is an img */
      if (el.tagName === 'IMG') {
        setThumbnail(el, videoId);
        return;
      }

      /* Otherwise find img inside */
      var img = el.querySelector('.video-thumb-img') || el.querySelector('img');
      if (img) {
        setThumbnail(img, videoId);
      }
    });
  });
})();
