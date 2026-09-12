/* Rugby AI / Matchday: accessible navigation, restrained motion and the existing licence integration. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const header = $('nav');
  const menu = $('navLinks');
  const menuButton = $('navToggle');
  const modal = $('payModal');
  const form = $('payForm');
  const submitButton = $('payBtn');
  const errorBox = $('payError');
  const success = $('paySuccess');
  const narrow = window.matchMedia('(max-width: 1000px)');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pageSurfaces = [document.querySelector('.utility'), header, $('main'), document.querySelector('.footer')].filter(Boolean);
  let opener = null;
  let pending = false;
  let requestNumber = 0;
  let selectedPlan = null;
  const plans = Object.freeze({
    monthly: Object.freeze({ name: 'Monthly', price: 29, months: 1, days: 30 }),
    '6months': Object.freeze({ name: '6 Months', price: 149, months: 6, days: 180 }),
    yearly: Object.freeze({ name: 'Annual', price: 249, months: 12, days: 365 })
  });
  const focusables = (root) => [...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), summary, [tabindex="0"]')].filter((el) => !el.hidden && el.getClientRects().length);
  function setMenu(open, returnFocus = false) {
    open = !!open && narrow.matches;
    menu.classList.toggle('open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    document.body.classList.toggle('menu-open', open);
    document.querySelector('.nav-launch').inert = open;
    menu.inert = narrow.matches && !open;
    $('main').inert = open;
    document.querySelector('.footer').inert = open;
    if (open) {
      menu.style.top = `${header.getBoundingClientRect().bottom}px`;
      requestAnimationFrame(() => focusables(menu)[0]?.focus());
    } else {
      menu.style.top = '';
      if (returnFocus) menuButton.focus();
    }
  }
  menuButton.addEventListener('click', () => setMenu(!menu.classList.contains('open'), true));
  narrow.addEventListener('change', () => {
    setMenu(false);
    if (!modal.hidden) pageSurfaces.forEach((surface) => { surface.inert = true; });
  });
  menu.inert = narrow.matches;
  let resizeFrame = 0;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      if (menu.classList.contains('open')) menu.style.top = `${header.getBoundingClientRect().bottom}px`;
    });
  }, { passive: true });

  function getHashTarget(hash) {
    try { return hash && hash.startsWith('#') ? $(decodeURIComponent(hash.slice(1))) : null; }
    catch { return null; }
  }
  function visitSection(hash, replace = false) {
    const target = getHashTarget(hash);
    if (!target) return;
    const nationPanel = target.closest('.nation-panel');
    if (nationPanel) document.dispatchEvent(new CustomEvent('rugby:nation', { detail: { id: nationPanel.id } }));
    if (!modal.hidden) closeModal(false);
    setMenu(false);
    const details = target.tagName === 'DETAILS' ? target : target.closest('details');
    if (details) details.open = true;
    if (location.hash !== hash) history[replace ? 'replaceState' : 'pushState'](null, '', hash);
    target.scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start' });
    // Move keyboard focus with navigation, keeping headings out of the regular tab order.
    const focusTarget = details ? details.querySelector('summary') : target;
    if (!focusTarget.hasAttribute('tabindex') && focusTarget.tagName !== 'SUMMARY') focusTarget.setAttribute('tabindex', '-1');
    focusTarget.focus({ preventScroll: true });
  }
  document.addEventListener('click', (event) => {
    const anchor = event.target.closest('a[href^="#"]');
    if (!anchor || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    const hash = anchor.getAttribute('href');
    if (!getHashTarget(hash)) return;
    event.preventDefault();
    visitSection(hash);
  });
  function restoreHash() {
    const target = getHashTarget(location.hash);
    if (target?.tagName === 'DETAILS') target.open = true;
  }
  restoreHash();
  window.addEventListener('hashchange', restoreHash);
  window.addEventListener('popstate', restoreHash);
  window.addEventListener('load', () => {
    if (location.hash && getHashTarget(location.hash)) requestAnimationFrame(() => visitSection(location.hash, true));
  }, { once: true });
  if ('IntersectionObserver' in window) {
    const links = [...menu.querySelectorAll('a[href^="#"]')];
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const hash = `#${entry.target.id}`;
        links.forEach((link) => {
          const active = link.getAttribute('href') === hash;
          link.classList.toggle('active', active);
          if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
        });
      }
    }, { rootMargin: '-15% 0px -65% 0px', threshold: 0 });
    ['hero', 'game', 'nations', 'leagues', 'lounge', 'about', 'history', 'plans', 'join', 'legal'].forEach((id) => { if ($(id)) observer.observe($(id)); });

  }

  // Public Firebase project configuration retained from the supplied website.
  let functions = null;
  let servicePromise = null;
  function loadSDK(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      const timeout = setTimeout(() => { script.remove(); reject(new Error('sdk-timeout')); }, 20000);
      script.onload = () => { clearTimeout(timeout); resolve(); };
      script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error('sdk-unavailable')); };
      document.head.appendChild(script);
    });
  }
  async function connectLicenceService() {
    if (functions) return functions;
    if (servicePromise) return servicePromise;
    servicePromise = (async () => {
      if (!window.firebase) await loadSDK('https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js');
      if (!window.firebase?.functions) await loadSDK('https://www.gstatic.com/firebasejs/9.23.0/firebase-functions-compat.js');
      if (!firebase.apps?.length) firebase.initializeApp({
        apiKey: 'AIzaSyAMZ0md0_DADjaI7Z4QujftjMp6e2P6gaw',
        authDomain: 'rugby-ai-61fd0.firebaseapp.com',
        projectId: 'rugby-ai-61fd0'
      });
      functions = firebase.app().functions('us-central1');
      return functions;
    })().catch(() => { servicePromise = null; return null; });
    return servicePromise;
  }
  function resetSubmitButton() {
    submitButton.disabled = false;
    submitButton.innerHTML = 'Continue with this pass <span aria-hidden="true">↗</span>';
    form.removeAttribute('aria-busy');
  }
  function openModal(type, trigger) {
    if (!plans[type]) return;
    setMenu(false);
    if (pending) {
      // Reopening a pending request resumes it; it must not create a duplicate licence.
      opener = trigger;
      modal.hidden = false;
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('modal-open');
      pageSurfaces.forEach((surface) => { surface.inert = true; });
      requestAnimationFrame(() => $('payClose').focus());
      return;
    }
    void connectLicenceService();
    selectedPlan = { type, ...plans[type] };
    opener = trigger;
    requestNumber += 1;
    pending = false;
    $('sumPlan').textContent = selectedPlan.name;
    $('sumDur').textContent = selectedPlan.months === 1 ? '1 month' : `${selectedPlan.months} months`;
    $('sumTotal').textContent = `$${selectedPlan.price}`;
    form.reset();
    form.hidden = false;
    success.hidden = true;
    errorBox.hidden = true;
    errorBox.textContent = '';
    resetSubmitButton();
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    pageSurfaces.forEach((surface) => { surface.inert = true; });
    requestAnimationFrame(() => $('payEmail').focus());
  }
  function closeModal(restoreFocus = true) {
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    pageSurfaces.forEach((surface) => { surface.inert = false; });
    if (restoreFocus && opener?.isConnected) opener.focus({ preventScroll: true });
  }
  document.querySelectorAll('[data-plan]').forEach((button) => {
    button.addEventListener('click', () => openModal(button.dataset.plan, button));
  });
  $('payClose').addEventListener('click', () => closeModal());
  $('successClose').addEventListener('click', () => closeModal());
  modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });
  document.addEventListener('keydown', (event) => {
    const dialogOpen = !modal.hidden;
    const menuOpen = menu.classList.contains('open');
    if (event.key === 'Escape') {
      if (dialogOpen) { event.preventDefault(); closeModal(); }
      else if (menuOpen) { event.preventDefault(); setMenu(false, true); }
    }
    if (event.key !== 'Tab' || (!dialogOpen && !menuOpen)) return;
    const options = dialogOpen ? focusables(modal) : [...focusables(menu), menuButton];
    const first = options[0], last = options[options.length - 1];
    if (!first) return;
    if (event.shiftKey && (document.activeElement === first || !options.includes(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !options.includes(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending || !selectedPlan || !form.reportValidity()) return;
    const email = $('payEmail').value.trim();
    const name = $('payName').value.trim();
    if (!name) {
      errorBox.textContent = 'Please enter your full name.';
      errorBox.hidden = false;
      $('payName').focus();
      return;
    }
    pending = true;
    const thisRequest = ++requestNumber;
    errorBox.hidden = true;
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="spin" aria-hidden="true"></span> Sending your request…';
    form.setAttribute('aria-busy', 'true');
    try {
      const service = await connectLicenceService();
      if (!service) throw new Error('service-unavailable');
      // Preserve the original callable and payload. This response is not proof of a payment.
      const result = await service.httpsCallable('generate_license_key_with_email')({
        email, name,
        subscription_type: selectedPlan.type,
        duration_days: selectedPlan.days,
        amount: selectedPlan.price
      });
      if (thisRequest !== requestNumber) return;
      if (!result || !result.data || result.data.error || result.data.success === false) throw new Error('request-failed');
      form.hidden = true;
      success.hidden = false;
      $('successMessage').textContent = result.data.email_sent === false
        ? 'Your request was received, but the email could not be delivered. Please contact support through the app to retrieve your licence key.'
        : 'Your request was received. Check your inbox and spam folder for your licence key and activation instructions.';
      if (!modal.hidden) $('successClose').focus();
    } catch {
      if (thisRequest !== requestNumber) return;
      errorBox.textContent = 'We could not complete your request. Please try again, or contact support through the app.';
      errorBox.hidden = false;
      resetSubmitButton();
    } finally {
      if (thisRequest === requestNumber) {
        pending = false;
        form.removeAttribute('aria-busy');
      }
    }
  });
})();
