/**
 * KettleBell Pro - Session Player
 *
 * Interactive workout session with timer, set tracking, and session logging.
 * Requires data-* attributes on #session-data element:
 *   data-workout-id, data-log-url, data-dashboard-url, data-csrf-token
 */

(function () {
  'use strict';

  /* ---- Config from data attributes ---- */
  const sessionData = document.getElementById('session-data');
  if (!sessionData) return;

  const CONFIG = {
    workoutId: sessionData.dataset.workoutId,
    plannedSessionId: sessionData.dataset.plannedSessionId || null,
    userId: sessionData.dataset.userId || 'unknown',
    logUrl: sessionData.dataset.logUrl,
    dashboardUrl: sessionData.dataset.dashboardUrl,
    csrfToken: sessionData.dataset.csrfToken,
    clientSessionId: createClientSessionId(),
  };

  const DRAFT_VERSION = 1;
  const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const DRAFT_KEY = [
    'kb-session-draft',
    'v' + DRAFT_VERSION,
    CONFIG.userId,
    CONFIG.workoutId,
    CONFIG.plannedSessionId || 'standalone',
  ].join(':');

  function createClientSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (char) {
      const random = Math.random() * 16 | 0;
      const value = char === 'x' ? random : (random & 0x3 | 0x8);
      return value.toString(16);
    });
  }

  /* ---- Estado general ---- */
  const totalSteps = parseInt(document.getElementById('total-steps-count').innerText);
  let currentStep = 0;
  let sessionStart = Date.now();
  let pendingPayload = null;
  let draftRecoveryBanner = null;
  let draftSaveTimer = null;

  /* Temporizador: modo 'chrono' (cuenta arriba) o 'interval' (trabajo/descanso) */
  let timerInterval = null;
  let isRunning = false;
  let seconds = 0;
  let phase = 'idle';       // 'work' | 'rest'
  let remaining = 0;
  let intervalPlan = null;  // {work, rest} o null

  /* Elements */
  const progressBar = document.getElementById('progress-bar');
  const currentStepNum = document.getElementById('current-step-num');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');
  const timerDisplay = document.getElementById('timer-display');
  const timerToggle = document.getElementById('timer-toggle');
  const timerPhase = document.getElementById('timer-phase');

  /* ---- Borrador local recuperable (sin credenciales ni CSRF) ---- */
  function readDraft() {
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY);
      if (!raw) return null;
      const draft = JSON.parse(raw);
      const exercisesAreValid = draft && (
        draft.exercises === undefined
        || (Array.isArray(draft.exercises)
          && draft.exercises.every(function (exercise) {
            return exercise && typeof exercise === 'object';
          }))
      );
      if (
        !draft
        || typeof draft !== 'object'
        || draft.version !== DRAFT_VERSION
        || !Number.isFinite(draft.savedAt)
        || !exercisesAreValid
      ) {
        window.localStorage.removeItem(DRAFT_KEY);
        return null;
      }
      if (Date.now() - draft.savedAt >= DRAFT_TTL_MS) {
        window.localStorage.removeItem(DRAFT_KEY);
        return null;
      }
      return draft;
    } catch (e) {
      try { window.localStorage.removeItem(DRAFT_KEY); } catch (storageError) { /* opcional */ }
      return null;
    }
  }

  function clearDraft() {
    try { window.localStorage.removeItem(DRAFT_KEY); } catch (e) { /* storage bloqueado */ }
  }

  function captureDraft() {
    document.querySelectorAll('.exercise-step[data-workout-exercise-id]').forEach(function (step) {
      initSetsTracker(step);
    });
    const exercises = Array.from(
      document.querySelectorAll('.exercise-step[data-workout-exercise-id]')
    ).map(function (step) {
      return {
        id: Number(step.dataset.workoutExerciseId),
        activeSets: Array.from(step.querySelectorAll('.set-bubble')).map(function (bubble, index) {
          return bubble.classList.contains('active') ? index : null;
        }).filter(function (index) { return index !== null; }),
        weight: (step.querySelector('.exercise-weight-input') || {}).value || '',
        reps: (step.querySelector('.exercise-reps-input') || {}).value || '',
        rpe: (step.querySelector('.exercise-rpe-input') || {}).value || '',
      };
    });
    const weightInput = document.getElementById('weight-input');
    const notesInput = document.getElementById('notes-input');
    return {
      version: DRAFT_VERSION,
      savedAt: Date.now(),
      currentStep: currentStep,
      elapsedSeconds: Math.max(0, Math.round((Date.now() - sessionStart) / 1000)),
      timerSeconds: seconds,
      timerPhase: phase,
      timerRemaining: remaining,
      clientSessionId: CONFIG.clientSessionId,
      selectedRpe: selectedRpe,
      weight: weightInput ? weightInput.value : '',
      notes: notesInput ? notesInput.value : '',
      exercises: exercises,
      pendingPayload: pendingPayload,
    };
  }

  function hasDraftProgress(draft) {
    if (!draft) return false;
    if (draft.pendingPayload || draft.currentStep > 0 || draft.elapsedSeconds > 0) return true;
    if (draft.selectedRpe || draft.weight || draft.notes) return true;
    return (draft.exercises || []).some(function (exercise) {
      return exercise.activeSets && exercise.activeSets.length > 0
        || exercise.weight || exercise.reps || exercise.rpe;
    });
  }

  function saveDraft() {
    // A recovery banner means the persisted draft is still the source of
    // truth. Do not let pagehide/interval saves from the untouched page
    // overwrite it before the user chooses restore or discard.
    if (sessionSaved || draftRecoveryBanner) return;
    const draft = captureDraft();
    if (!hasDraftProgress(draft)) return;
    try { window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch (e) { /* opcional */ }
  }

  function scheduleDraftSave() {
    clearTimeout(draftSaveTimer);
    draftSaveTimer = setTimeout(saveDraft, 250);
  }

  function hideDraftRecovery() {
    if (draftRecoveryBanner) draftRecoveryBanner.remove();
    draftRecoveryBanner = null;
  }

  function applyDraft(draft) {
    currentStep = Math.max(0, Math.min(totalSteps, Number(draft.currentStep) || 0));
    sessionStart = Date.now() - (Math.max(0, Number(draft.elapsedSeconds) || 0) * 1000);
    const restoredTimerSeconds = Math.max(0, Number(draft.timerSeconds) || 0);
    seconds = restoredTimerSeconds;
    if (draft.clientSessionId) CONFIG.clientSessionId = draft.clientSessionId;
    selectedRpe = draft.selectedRpe || null;
    const weightInput = document.getElementById('weight-input');
    const notesInput = document.getElementById('notes-input');
    if (weightInput && draft.weight !== undefined) weightInput.value = draft.weight;
    if (notesInput && draft.notes !== undefined) notesInput.value = draft.notes;
    (draft.exercises || []).forEach(function (exercise) {
      const step = document.querySelector(
        '.exercise-step[data-workout-exercise-id="' + exercise.id + '"]'
      );
      if (!step) return;
      initSetsTracker(step);
      const weight = step.querySelector('.exercise-weight-input');
      const reps = step.querySelector('.exercise-reps-input');
      const rpe = step.querySelector('.exercise-rpe-input');
      if (weight) weight.value = exercise.weight || '';
      if (reps) reps.value = exercise.reps || '';
      if (rpe) rpe.value = exercise.rpe || '';
      const active = new Set(exercise.activeSets || []);
      step.querySelectorAll('.set-bubble').forEach(function (bubble, index) {
        bubble.classList.toggle('active', active.has(index));
      });
    });
    pendingPayload = draft.pendingPayload || null;
    updateUI();
    seconds = restoredTimerSeconds;
    if (currentStep < totalSteps) {
      if (intervalPlan && Number.isFinite(Number(draft.timerRemaining))) {
        remaining = Math.max(0, Number(draft.timerRemaining));
        phase = draft.timerPhase || phase;
      }
      updateTimerDisplay();
    }
    if (selectedRpe) {
      initRpeScale();
      document.querySelectorAll('.rpe-bubble').forEach(function (bubble) {
        bubble.classList.toggle('active', Number(bubble.innerText) === Number(selectedRpe));
      });
    }
    hideDraftRecovery();
    const feedback = document.getElementById('metrics-feedback');
    if (pendingPayload && feedback) {
      feedback.innerText = 'Hay un guardado pendiente. Pulsa Guardar sesión o espera a recuperar conexión.';
    }
  }

  function showDraftRecovery(draft) {
    const parent = document.querySelector('.session-section .container-sm') || document.body;
    draftRecoveryBanner = document.createElement('div');
    draftRecoveryBanner.className = 'draft-recovery-banner';
    draftRecoveryBanner.innerHTML = '<div><strong>Encontramos un borrador de esta sesión.</strong>'
      + '<span>Se conserva durante 7 días en este dispositivo.</span></div>'
      + '<div class="draft-recovery-actions"><button type="button" class="btn btn-primary btn-sm" data-draft-restore>Continuar borrador</button>'
      + '<button type="button" class="btn btn-outline btn-sm" data-draft-discard>Descartar</button></div>';
    parent.insertBefore(draftRecoveryBanner, parent.firstChild);
    draftRecoveryBanner.querySelector('[data-draft-restore]').onclick = function () { applyDraft(draft); };
    draftRecoveryBanner.querySelector('[data-draft-discard]').onclick = function () {
      clearDraft();
      pendingPayload = null;
      CONFIG.clientSessionId = createClientSessionId();
      hideDraftRecovery();
    };
  }

  /* ---- Sonido (WebAudio, sin assets externos) ---- */
  let audioCtx = null;

  function beep(times, freq) {
    times = times || 1;
    freq = freq || 880;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      for (let i = 0; i < times; i++) {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.value = freq;
        gain.gain.value = 0.15;
        osc.connect(gain).connect(audioCtx.destination);
        const start = audioCtx.currentTime + i * 0.25;
        osc.start(start);
        osc.stop(start + 0.15);
      }
    } catch (e) { /* sin audio disponible */ }
  }

  /* ---- Parseo del objetivo ---- */
  function parseIntervalPlan(repsText) {
    if (!repsText) return null;
    const text = repsText.toLowerCase();
    const workRest = text.match(/(\d+)\s*s(?:egs?)?[^\/]*\/\s*(\d+)\s*s(?:egs?)?/);
    if (workRest) {
      return { work: parseInt(workRest[1]), rest: parseInt(workRest[2]) };
    }
    const timed = text.match(/(?:\d+\s*-\s*)?(\d+)\s*seg/);
    if (timed) {
      return { work: parseInt(timed[1]), rest: 0 };
    }
    return null;
  }

  /* ---- UI helpers ---- */
  function formatTime(total) {
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return mins.toString().padStart(2, '0') + ':' + secs.toString().padStart(2, '0');
  }

  function setPhaseLabel(text, cls) {
    timerPhase.innerText = text;
    timerPhase.className = 'timer-phase' + (cls ? ' ' + cls : '');
  }

  function updateTimerDisplay() {
    timerDisplay.innerText = formatTime(intervalPlan ? remaining : seconds);
  }

  function updateUI() {
    for (let i = 0; i < totalSteps; i++) {
      const el = document.getElementById('step-' + i);
      if (el) {
        const isCurrent = (i === currentStep);
        el.style.display = isCurrent ? 'flex' : 'none';
        if (isCurrent) initSetsTracker(el);
      }
    }

    const percent = ((currentStep + 1) / totalSteps) * 100;
    progressBar.style.width = percent + '%';
    currentStepNum.innerText = Math.min(currentStep + 1, totalSteps);
    prevBtn.disabled = currentStep === 0;

    if (currentStep >= totalSteps) {
      document.getElementById('step-complete').style.display = 'flex';
      document.querySelector('.controls-area').style.display = 'none';
      document.querySelector('.session-header').style.display = 'none';
      const elapsed = Math.round((Date.now() - sessionStart) / 1000);
      document.getElementById('final-time-display').innerText = formatTime(elapsed);
      initRpeScale();
      beep(3, 1046);
    } else {
      nextBtn.innerText = (currentStep === totalSteps - 1) ? 'Finalizar Entrenamiento' : 'Siguiente →';
      setupTimerForStep();
    }
  }

  /* ---- Temporizador ---- */
  function setupTimerForStep() {
    stopTicking();
    const stepEl = document.getElementById('step-' + currentStep);
    intervalPlan = parseIntervalPlan(stepEl ? stepEl.dataset.reps : '');
    seconds = 0;
    if (intervalPlan) {
      phase = 'work';
      remaining = intervalPlan.work;
      setPhaseLabel('Trabajo ' + intervalPlan.work + 's' + (intervalPlan.rest ? ' / descanso ' + intervalPlan.rest + 's' : ''), '');
    } else {
      phase = 'idle';
      setPhaseLabel('Cronómetro libre (marca tus series)', '');
    }
    updateTimerDisplay();
  }

  function stopTicking() {
    clearInterval(timerInterval);
    timerInterval = null;
    isRunning = false;
    timerToggle.innerText = '⏯️ Iniciar';
  }

  function tick() {
    if (!intervalPlan) {
      seconds++;
      updateTimerDisplay();
      scheduleDraftSave();
      return;
    }

    remaining--;
    if (remaining > 0) {
      updateTimerDisplay();
      return;
    }

    if (phase === 'work' && intervalPlan.rest > 0) {
      beep(1);
      phase = 'rest';
      remaining = intervalPlan.rest;
      setPhaseLabel('Descanso', 'rest');
    } else {
      beep(2);
      const setDone = markNextSet();
      if (setDone.allDone) {
        stopTicking();
        setPhaseLabel('¡Ejercicio completado!', 'work');
        setTimeout(nextStep, 800);
        return;
      }
      phase = 'work';
      remaining = intervalPlan.work;
      setPhaseLabel('Trabajo (serie ' + setDone.nextSet + ')', 'work');
    }
    updateTimerDisplay();
    scheduleDraftSave();
  }

  /* ---- Controles globales (exposed para onclick en HTML) ---- */
  window.toggleTimer = function () {
    if (isRunning) {
      stopTicking();
    } else {
      if (intervalPlan && phase === 'work') setPhaseLabel('Trabajo', 'work');
      timerInterval = setInterval(tick, 1000);
      isRunning = true;
      timerToggle.innerText = '⏸️ Pausar';
      beep(1, 660);
    }
  };

  window.resetTimer = function () {
    setupTimerForStep();
    scheduleDraftSave();
  };

  /* ---- Series ---- */
  function markNextSet() {
    const stepEl = document.getElementById('step-' + currentStep);
    const bubbles = stepEl ? stepEl.querySelectorAll('.set-bubble') : [];
    let marked = 0;
    let next = null;
    bubbles.forEach(function (b) {
      if (b.classList.contains('active')) { marked++; }
      else if (next === null) { next = b; }
    });
    if (next) {
      next.classList.add('active');
      marked++;
    }
    return { allDone: marked >= bubbles.length, nextSet: marked + 1 };
  }

  window.nextStep = function () {
    if (currentStep < totalSteps) {
      currentStep++;
      updateUI();
      scheduleDraftSave();
    }
  };

  window.prevStep = function () {
    if (currentStep > 0) {
      currentStep--;
      updateUI();
      scheduleDraftSave();
    }
  };

  function initSetsTracker(stepElement) {
    const tracker = stepElement.querySelector('.sets-tracker');
    if (!tracker || tracker.dataset.initialized) return;

    const totalSets = parseInt(tracker.dataset.totalSets);
    const bubblesContainer = tracker.querySelector('.sets-bubbles');
    bubblesContainer.innerHTML = '';

    for (let i = 1; i <= totalSets; i++) {
      const bubble = document.createElement('div');
      bubble.classList.add('set-bubble');
      bubble.innerText = i;
      bubble.onclick = function () {
        this.classList.toggle('active');
        scheduleDraftSave();
        if (i === totalSets && this.classList.contains('active')) {
          const allBubbles = bubblesContainer.querySelectorAll('.set-bubble');
          const allActive = Array.from(allBubbles).every(function (b) { return b.classList.contains('active'); });
          if (allActive) setTimeout(nextStep, 500);
        }
      };
      bubblesContainer.appendChild(bubble);
    }
    tracker.dataset.initialized = 'true';
  }

  function initExerciseMetrics() {
    document.querySelectorAll('.exercise-rpe-input').forEach(function (select) {
      if (select.dataset.initialized) return;
      for (let value = 1; value <= 10; value++) {
        const option = document.createElement('option');
        option.value = value;
        option.innerText = value;
        select.appendChild(option);
      }
      select.dataset.initialized = 'true';
    });
  }

  function numberOrNull(value) {
    const trimmed = (value || '').trim();
    return trimmed === '' ? null : Number(trimmed);
  }

  function collectExerciseLogs() {
    const rows = [];
    document.querySelectorAll('.exercise-step[data-workout-exercise-id]').forEach(function (step) {
      const weightInput = step.querySelector('.exercise-weight-input');
      const repsInput = step.querySelector('.exercise-reps-input');
      const rpeInput = step.querySelector('.exercise-rpe-input');
      const activeSets = step.querySelectorAll('.set-bubble.active').length;
      const weight = numberOrNull(weightInput ? weightInput.value : '');
      const reps = numberOrNull(repsInput ? repsInput.value : '');
      const rpe = numberOrNull(rpeInput ? rpeInput.value : '');

      // No se crea un registro artificial solo por mostrar una sugerencia.
      if (activeSets === 0 && weight === null && reps === null && rpe === null) return;
      rows.push({
        workout_exercise_id: Number(step.dataset.workoutExerciseId),
        completed: activeSets > 0,
        sets_completed: activeSets,
        reps_completed: reps,
        weight: weight,
        rpe: rpe,
      });
    });
    return rows;
  }

  /* ---- Registro de la sesión ---- */
  let selectedRpe = null;
  let sessionSaved = false;

  function initRpeScale() {
    const scale = document.getElementById('rpe-scale');
    if (scale.dataset.initialized) return;
    for (let i = 1; i <= 10; i++) {
      const bubble = document.createElement('button');
      bubble.type = 'button';
      bubble.classList.add('rpe-bubble');
      bubble.innerText = i;
      bubble.onclick = function () {
        selectedRpe = i;
        scale.querySelectorAll('.rpe-bubble').forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');
        scheduleDraftSave();
      };
      scale.appendChild(bubble);
    }
    scale.dataset.initialized = 'true';
  }

  function buildSessionPayload() {
    const weightInput = document.getElementById('weight-input');
    const notesInput = document.getElementById('notes-input');
    return {
      workout_id: CONFIG.workoutId,
      planned_session_id: CONFIG.plannedSessionId,
      client_session_id: CONFIG.clientSessionId,
      duration_minutes: Math.max(1, Math.round((Date.now() - sessionStart) / 60000)),
      rpe: selectedRpe,
      kettlebell_weight: weightInput && weightInput.value ? parseFloat(weightInput.value) : null,
      notes: notesInput ? notesInput.value.trim() : '',
      exercise_logs: collectExerciseLogs(),
    };
  }

  function showPendingFeedback(message) {
    const feedback = document.getElementById('metrics-feedback');
    if (!feedback) return;
    feedback.innerHTML = message + ' <button type="button" class="btn-link-muted" id="retry-session-save">Reintentar ahora</button>';
    const retry = document.getElementById('retry-session-save');
    if (retry) retry.onclick = sendPendingPayload;
  }

  function sendPendingPayload() {
    if (sessionSaved || !pendingPayload) return Promise.resolve();
    const feedback = document.getElementById('metrics-feedback');
    const saveBtn = document.getElementById('save-session-btn');
    if (!navigator.onLine) {
      if (saveBtn) saveBtn.disabled = false;
      showPendingFeedback('Sin conexión: conservamos el registro en este dispositivo.');
      saveDraft();
      return Promise.resolve();
    }
    if (saveBtn) saveBtn.disabled = true;
    return fetch(CONFIG.logUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CONFIG.csrfToken,
      },
      body: JSON.stringify(pendingPayload),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok || body.status !== 'success') throw new Error(body.message || 'bad status');
        return body;
      });
    }).then(function () {
      sessionSaved = true;
      pendingPayload = null;
      clearDraft();
      if (feedback) feedback.innerText = '✅ Sesión guardada. Redirigiendo a tu panel...';
      document.getElementById('skip-save-link').style.display = 'none';
      setTimeout(function () { window.location.href = CONFIG.dashboardUrl; }, 1200);
    }).catch(function () {
      if (saveBtn) saveBtn.disabled = false;
      showPendingFeedback('No se pudo enviar todavía. El borrador queda guardado para reintentar.');
      saveDraft();
    });
  }

  window.saveSession = function () {
    if (sessionSaved) return;
    pendingPayload = buildSessionPayload();
    saveDraft();
    sendPendingPayload();
  };

  document.addEventListener('input', scheduleDraftSave);
  document.addEventListener('change', scheduleDraftSave);
  window.addEventListener('online', function () {
    if (pendingPayload) sendPendingPayload();
  });
  window.addEventListener('pagehide', saveDraft);
  window.addEventListener('beforeunload', saveDraft);

  /* ---- Initialize ---- */
  initExerciseMetrics();
  updateUI();
  const existingDraft = readDraft();
  if (existingDraft && hasDraftProgress(existingDraft)) showDraftRecovery(existingDraft);
  window.setInterval(saveDraft, 5000);
})();
