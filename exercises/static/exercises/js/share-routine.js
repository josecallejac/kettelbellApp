/**
 * KettleBell Pro - Share/Export Routine Module
 *
 * Generates a shareable image of a workout using Canvas API.
 * Supports Web Share API for mobile sharing and download for desktop.
 */

const KBShare = (function () {
  'use strict';

  const COLORS = {
    bg: '#0f172a',
    card: '#1e293b',
    border: '#334155',
    primary: '#6366f1',
    primaryLight: '#818cf8',
    accent: '#f59e0b',
    text: '#f1f5f9',
    textSecondary: '#cbd5e1',
    textMuted: '#94a3b8',
    green: '#22c55e',
    yellow: '#f59e0b',
    red: '#ef4444',
  };

  const DIFFICULTY_COLORS = {
    beginner: COLORS.green,
    intermediate: COLORS.yellow,
    advanced: COLORS.red,
  };

  const DIFFICULTY_LABELS = {
    beginner: 'Principiante',
    intermediate: 'Intermedio',
    advanced: 'Avanzado',
  };

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = text.split(' ');
    let line = '';
    let currentY = y;
    const lines = [];

    for (const word of words) {
      const testLine = line + (line ? ' ' : '') + word;
      const metrics = ctx.measureText(testLine);
      if (metrics.width > maxWidth && line) {
        lines.push({ text: line, y: currentY });
        line = word;
        currentY += lineHeight;
      } else {
        line = testLine;
      }
    }
    lines.push({ text: line, y: currentY });
    return lines;
  }

  function generateImage(data) {
    const canvas = document.createElement('canvas');
    const dpr = 2;
    const W = 800;
    const padding = 40;

    /* Calculate height needed */
    const exerciseRowHeight = 52;
    const headerHeight = 180;
    const footerHeight = 80;
    const exercisesHeight = data.exercises.length * exerciseRowHeight + 60;
    const H = headerHeight + exercisesHeight + footerHeight;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    /* Background */
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    /* Header gradient bar */
    const gradient = ctx.createLinearGradient(0, 0, W, 0);
    gradient.addColorStop(0, '#667eea');
    gradient.addColorStop(1, '#764ba2');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, 6);

    /* Logo */
    let y = padding + 10;
    ctx.fillStyle = COLORS.primary;
    roundRect(ctx, padding, y - 8, 46, 22, 8);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 13px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('KB', padding + 10, y + 7);

    ctx.fillStyle = COLORS.text;
    ctx.font = 'bold 16px Inter, sans-serif';
    ctx.fillText('KettleBell Pro', padding + 56, y + 7);

    /* Workout title */
    y += 50;
    ctx.fillStyle = COLORS.text;
    ctx.font = 'bold 32px Inter, sans-serif';
    ctx.fillText(data.title, padding, y);

    /* Description */
    y += 30;
    ctx.fillStyle = COLORS.textSecondary;
    ctx.font = '15px Inter, sans-serif';
    const descLines = wrapText(ctx, data.description || '', padding, y, W - padding * 2, 22);
    descLines.forEach(l => ctx.fillText(l.text, padding, l.y));
    y = descLines[descLines.length - 1].y + 20;

    /* Tags: difficulty + duration */
    const diffColor = DIFFICULTY_COLORS[data.difficulty] || COLORS.primary;
    const diffLabel = DIFFICULTY_LABELS[data.difficulty] || data.difficulty;

    ctx.fillStyle = diffColor;
    roundRect(ctx, padding, y, ctx.measureText(diffLabel).width + 24, 28, 8);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12px Inter, sans-serif';
    ctx.fillText(diffLabel, padding + 12, y + 18);

    const durLabel = `⏱ ${data.duration} min`;
    const durX = padding + ctx.measureText(diffLabel).width + 36;
    ctx.fillStyle = COLORS.card;
    roundRect(ctx, durX, y, ctx.measureText(durLabel).width + 24, 28, 8);
    ctx.fill();
    ctx.strokeStyle = COLORS.border;
    roundRect(ctx, durX, y, ctx.measureText(durLabel).width + 24, 28, 8);
    ctx.stroke();
    ctx.fillStyle = COLORS.primaryLight;
    ctx.fillText(durLabel, durX + 12, y + 18);

    y += 50;

    /* Exercises header */
    ctx.fillStyle = COLORS.primary;
    ctx.fillRect(padding, y, 4, 24);
    ctx.fillStyle = COLORS.text;
    ctx.font = 'bold 18px Inter, sans-serif';
    ctx.fillText('Ejercicios', padding + 16, y + 18);
    y += 40;

    /* Exercise rows */
    data.exercises.forEach((ex, i) => {
      const rowY = y + i * exerciseRowHeight;

      /* Row background */
      ctx.fillStyle = i % 2 === 0 ? COLORS.card : 'rgba(30, 41, 59, 0.5)';
      roundRect(ctx, padding, rowY, W - padding * 2, exerciseRowHeight - 8, 8);
      ctx.fill();

      /* Number circle */
      ctx.fillStyle = COLORS.primary;
      ctx.beginPath();
      ctx.arc(padding + 24, rowY + (exerciseRowHeight - 8) / 2, 14, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(String(i + 1), padding + 24, rowY + (exerciseRowHeight - 8) / 2 + 4);
      ctx.textAlign = 'left';

      /* Exercise name */
      ctx.fillStyle = COLORS.text;
      ctx.font = '600 15px Inter, sans-serif';
      ctx.fillText(ex.name, padding + 48, rowY + 24);

      /* Sets x Reps */
      ctx.fillStyle = COLORS.primaryLight;
      ctx.font = 'bold 14px Inter, sans-serif';
      const specText = `${ex.sets}×${ex.reps}`;
      ctx.fillText(specText, W - padding - ctx.measureText(specText).width - 10, rowY + 24);

      /* Notes (if any) */
      if (ex.notes) {
        ctx.fillStyle = COLORS.textMuted;
        ctx.font = '12px Inter, sans-serif';
        ctx.fillText(ex.notes, padding + 48, rowY + 40);
      }
    });

    /* Footer */
    const footerY = H - footerHeight + 20;
    ctx.fillStyle = COLORS.border;
    ctx.fillRect(padding, footerY, W - padding * 2, 1);

    ctx.fillStyle = COLORS.textMuted;
    ctx.font = '13px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Generado con KettleBell Pro — kettlebellpro.app', W / 2, footerY + 30);
    ctx.textAlign = 'left';

    return canvas;
  }

  async function shareRoutine(data) {
    const canvas = generateImage(data);

    if (navigator.share && navigator.canShare) {
      try {
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
        const file = new File([blob], `rutina-${data.slug}.png`, { type: 'image/png' });

        if (navigator.canShare({ files: [file] })) {
          await navigator.share({
            title: data.title,
            text: `Mi rutina de kettlebell: ${data.title}`,
            files: [file],
          });
          return true;
        }

        /* Fallback: share without file */
        await navigator.share({
          title: data.title,
          text: `Mi rutina de kettlebell: ${data.title} (${data.exercises.length} ejercicios, ${data.duration} min)`,
        });
        return true;
      } catch (e) {
        if (e.name === 'AbortError') return false;
        console.log('Share failed, falling back to download', e);
      }
    }

    downloadImage(canvas, data.slug);
    return true;
  }

  function downloadImage(canvas, slug) {
    const link = document.createElement('a');
    link.download = `rutina-${slug || 'workout'}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }

  async function loadAndShare(slug) {
    try {
      const response = await fetch(`/api/workout-export/${slug}/`);
      if (!response.ok) throw new Error('Failed to load workout data');
      const data = await response.json();
      return shareRoutine(data);
    } catch (e) {
      console.error('Error sharing routine:', e);
      alert('No se pudo generar la imagen. Inténtalo de nuevo.');
      return false;
    }
  }

  async function loadAndDownload(slug) {
    try {
      const response = await fetch(`/api/workout-export/${slug}/`);
      if (!response.ok) throw new Error('Failed to load workout data');
      const data = await response.json();
      const canvas = generateImage(data);
      downloadImage(canvas, data.slug);
      return true;
    } catch (e) {
      console.error('Error downloading routine:', e);
      alert('No se pudo generar la imagen. Inténtalo de nuevo.');
      return false;
    }
  }

  return { generateImage, shareRoutine, downloadImage, loadAndShare, loadAndDownload };
})();
