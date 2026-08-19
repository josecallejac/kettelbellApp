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
    logUrl: sessionData.dataset.logUrl,
    dashboardUrl: sessionData.dataset.dashboardUrl,
    csrfToken: sessionData.dataset.csrfToken,
  };

  /* ---- Estado general ---- */
  const totalSteps = parseInt(document.getElementById('total-steps-count').innerText);
  let currentStep = 0;
  const sessionStart = Date.now();

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
    }
  };

  window.prevStep = function () {
    if (currentStep > 0) {
      currentStep--;
      updateUI();
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
      };
      scale.appendChild(bubble);
    }
    scale.dataset.initialized = 'true';
  }

  window.saveSession = function () {
    if (sessionSaved) return;
    const feedback = document.getElementById('metrics-feedback');
    const saveBtn = document.getElementById('save-session-btn');
    const elapsedMinutes = Math.max(1, Math.round((Date.now() - sessionStart) / 60000));
    const weightRaw = document.getElementById('weight-input').value;
    const payload = {
      workout_id: CONFIG.workoutId,
      duration_minutes: elapsedMinutes,
      rpe: selectedRpe,
      kettlebell_weight: weightRaw ? parseFloat(weightRaw) : null,
      notes: document.getElementById('notes-input').value.trim(),
    };

    saveBtn.disabled = true;
    fetch(CONFIG.logUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CONFIG.csrfToken,
      },
      body: JSON.stringify(payload),
    }).then(function (res) {
      if (!res.ok) throw new Error('bad status');
      sessionSaved = true;
      feedback.innerText = '✅ Sesión guardada. Redirigiendo a tu panel...';
      document.getElementById('skip-save-link').style.display = 'none';
      setTimeout(function () { window.location.href = CONFIG.dashboardUrl; }, 1200);
    }).catch(function () {
      saveBtn.disabled = false;
      feedback.innerText = 'No se pudo guardar la sesión. Revisa los datos e inténtalo de nuevo.';
    });
  };

  /* ---- Initialize ---- */
  updateUI();
})();
