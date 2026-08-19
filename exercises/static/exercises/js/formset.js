/**
 * KettleBell Pro - Dynamic Formset
 *
 * Adds new rows to a Django inline formset.
 * Requires:
 *   #formset-container — container for form rows
 *   #add-exercise-btn — button to add new row
 *   #id_exercises-TOTAL_FORMS — Django management form counter
 *   #empty-form — <template> or hidden div with __prefix__ placeholder
 */

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var formsetContainer = document.getElementById('formset-container');
    var addBtn = document.getElementById('add-exercise-btn');
    var totalForms = document.getElementById('id_exercises-TOTAL_FORMS');
    var emptyFormEl = document.getElementById('empty-form');

    if (!formsetContainer || !addBtn || !totalForms || !emptyFormEl) return;

    var emptyFormTemplate = emptyFormEl.innerHTML;

    addBtn.addEventListener('click', function () {
      var formIdx = totalForms.value;
      var newFormHtml = emptyFormTemplate.replace(/__prefix__/g, formIdx);

      var div = document.createElement('div');
      div.innerHTML = newFormHtml;
      var newRow = div.firstElementChild;

      /* Update row number visually */
      var rowNum = newRow.querySelector('.row-number');
      if (rowNum) {
        rowNum.innerText = '#' + (parseInt(formIdx) + 1);
      }

      formsetContainer.appendChild(newRow);
      totalForms.value = parseInt(formIdx) + 1;
    });
  });
})();
