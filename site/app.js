'use strict';

const root = document.documentElement;
const langBtn = document.getElementById('langBtn');
const TITLES = {
  en: 'ClaimLedger — The decision ledger for AI agents',
  zh: 'ClaimLedger — 给 AI Agent 的决策账本',
};
const DESCRIPTIONS = {
  en: 'A local-first decision ledger for AI agents. Record decisions once, keep their status and provenance, refuse silent conflicts. Zero dependencies, zero model calls.',
  zh: '给 AI Agent 的本地决策账本。决策只记录一次，保留状态与出处，拒绝静默冲突。零第三方依赖，零模型调用。',
};

function preferredLang() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get('lang');
  if (query === 'zh' || query === 'en') return query;
  let saved = null;
  try { saved = localStorage.getItem('claimledger.lang'); } catch (error) {}
  if (saved === 'zh' || saved === 'en') return saved;
  return (navigator.language || 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en';
}

let currentLang = preferredLang();

function applyLang(lang, { persist = true } = {}) {
  currentLang = lang === 'zh' ? 'zh' : 'en';
  root.dataset.lang = currentLang;
  root.lang = currentLang === 'zh' ? 'zh-CN' : 'en';

  document.querySelectorAll('[data-en]').forEach((element) => {
    const value = element.getAttribute(currentLang === 'zh' ? 'data-zh' : 'data-en');
    if (value !== null) element.textContent = value;
  });
  document.querySelectorAll('[data-en-html]').forEach((element) => {
    const value = element.getAttribute(currentLang === 'zh' ? 'data-zh-html' : 'data-en-html');
    if (value !== null) element.innerHTML = value;
  });
  document.querySelectorAll('[data-en-aria]').forEach((element) => {
    const value = element.getAttribute(currentLang === 'zh' ? 'data-zh-aria' : 'data-en-aria');
    if (value !== null) element.setAttribute('aria-label', value);
  });
  document.querySelectorAll('[data-href-en]').forEach((element) => {
    const value = element.getAttribute(currentLang === 'zh' ? 'data-href-zh' : 'data-href-en');
    if (value !== null) element.setAttribute('href', value);
  });

  document.title = TITLES[currentLang];
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.setAttribute('content', DESCRIPTIONS[currentLang]);
  langBtn.textContent = currentLang === 'zh' ? 'EN' : '中文';
  langBtn.setAttribute('aria-label', currentLang === 'zh' ? 'Switch to English' : '切换到中文');

  const openCaption = document.getElementById('lightbox');
  if (openCaption && !openCaption.hidden) {
    const figure = document.querySelector('.shot[data-full="' + document.getElementById('lightboxImg').getAttribute('src') + '"]');
    if (figure) {
      const cap = figure.getAttribute(currentLang === 'zh' ? 'data-cap-zh' : 'data-cap-en') || '';
      document.getElementById('lightboxCap').textContent = cap;
    }
  }

  if (persist) {
    try { localStorage.setItem('claimledger.lang', currentLang); } catch (error) {}
  }
}

langBtn.addEventListener('click', () => applyLang(currentLang === 'zh' ? 'en' : 'zh'));

/* Copy buttons: copy the text of the target <pre>. */
function legacyCopy(text) {
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (error) { ok = false; }
  document.body.removeChild(area);
  return ok;
}

document.querySelectorAll('.copy-btn').forEach((button) => {
  button.addEventListener('click', async () => {
    const target = document.getElementById(button.getAttribute('data-copy-target'));
    if (!target) return;
    const text = target.innerText;
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (error) {
      ok = legacyCopy(text);
    }
    button.textContent = ok
      ? (currentLang === 'zh' ? '已复制' : 'Copied')
      : (currentLang === 'zh' ? '复制失败' : 'Copy failed');
    setTimeout(() => {
      button.textContent = currentLang === 'zh' ? '复制' : 'Copy';
    }, 1700);
  });
});

/* Screenshot lightbox. */
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightboxImg');
const lightboxCap = document.getElementById('lightboxCap');
let lastTrigger = null;

function openLightbox(trigger) {
  lastTrigger = trigger;
  lightboxImg.src = trigger.getAttribute('data-full');
  lightboxImg.alt = trigger.querySelector('img')?.alt || '';
  lightboxCap.textContent = trigger.getAttribute(currentLang === 'zh' ? 'data-cap-zh' : 'data-cap-en') || '';
  lightbox.hidden = false;
  document.body.style.overflow = 'hidden';
  lightbox.querySelector('.lightbox__close').focus();
}

function closeLightbox() {
  lightbox.hidden = true;
  document.body.style.overflow = '';
  lightboxImg.src = '';
  if (lastTrigger) lastTrigger.focus();
}

document.querySelectorAll('.shot').forEach((shot) => {
  shot.addEventListener('click', () => openLightbox(shot));
});
lightbox.querySelectorAll('[data-close-lightbox]').forEach((element) => {
  element.addEventListener('click', closeLightbox);
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !lightbox.hidden) closeLightbox();
  if (event.key === 'Tab' && !lightbox.hidden) {
    const focusable = Array.from(lightbox.querySelectorAll('button:not([disabled]), [href]'))
      .filter((element) => element.offsetParent !== null);
    if (focusable.length) {
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }
});

/* Scroll reveal. */
const revealItems = document.querySelectorAll('.reveal');
if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('is-in'));
}

applyLang(currentLang, { persist: false });
