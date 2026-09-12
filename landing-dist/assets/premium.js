/* Rugby AI / Campaign motion and editorial interactions. No synthetic match data. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const gsap = window.gsap;
  const ST = window.ScrollTrigger;
  const animationReady = !!(gsap && ST);
  if (animationReady) gsap.registerPlugin(ST);
  let motion = !reduced.matches;
  let animationContext = null;
  let introPlayed = false;

  const panels = [...document.querySelectorAll('.nation-panel')];
  const tabs = [...document.querySelectorAll('[data-nation]')];
  let selectedNation = 0;
  function selectNation(index, focus = false, animate = true) {
    selectedNation = (index + panels.length) % panels.length;
    panels.forEach((panel, i) => {
      panel.hidden = i !== selectedNation;
      panel.inert = i !== selectedNation;
      tabs[i].setAttribute('aria-selected', String(i === selectedNation));
      tabs[i].tabIndex = i === selectedNation ? 0 : -1;
    });
    const active = panels[selectedNation];
    $('nationPosition').textContent = `${String(selectedNation + 1).padStart(2, '0')} / ${String(panels.length).padStart(2, '0')}`;
    if (focus) tabs[selectedNation].focus({ preventScroll: true });
    if (animationReady) {
      const copy = active.querySelector('.nation-panel-copy');
      const picture = active.querySelector('.nation-backdrop img');
      gsap.killTweensOf([copy, picture]);
      gsap.set([copy, picture], { clearProps: 'opacity,transform' });
      if (motion && animate) {
        gsap.fromTo(active.querySelectorAll('.glyph'), { yPercent: 65, opacity: 0 }, { yPercent: 0, opacity: 1, duration: .6, stagger: .018, ease: 'power3.out', clearProps: 'opacity,transform' });
        gsap.fromTo(copy, { opacity: 0, y: 15 }, { opacity: 1, y: 0, duration: .55, ease: 'power2.out', clearProps: 'opacity,transform' });
        gsap.fromTo(picture, { opacity: .4, scale: 1.04 }, { opacity: 1, scale: 1, duration: .8, ease: 'power2.out', clearProps: 'opacity,transform' });
      }
    }
  }
  if (panels.length && panels.length === tabs.length) {
    $('nationTabs').hidden = false;
    document.querySelector('.nation-arrows').hidden = false;
    let initialHash = '';
    try { initialHash = decodeURIComponent(location.hash.slice(1)); } catch {}
    const initial = panels.findIndex((panel) => panel.id === initialHash);
    selectNation(initial >= 0 ? initial : 0, false, false);
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => selectNation(i));
      tab.addEventListener('keydown', (event) => {
        let next = null;
        if (event.key === 'ArrowRight') next = i + 1;
        if (event.key === 'ArrowLeft') next = i - 1;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = panels.length - 1;
        if (next !== null) { event.preventDefault(); selectNation(next, true); }
      });
    });
    $('nationNext').addEventListener('click', () => selectNation(selectedNation + 1));
    $('nationPrev').addEventListener('click', () => selectNation(selectedNation - 1));
    document.addEventListener('rugby:nation', (event) => {
      const index = panels.findIndex((panel) => panel.id === event.detail?.id);
      if (index >= 0) selectNation(index, false, false);
    });
    const stage = document.querySelector('.nation-stage');
    let start = null;
    stage.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'touch') start = { x: event.clientX, y: event.clientY, id: event.pointerId };
    }, { passive: true });
    stage.addEventListener('pointerup', (event) => {
      if (!start || start.id !== event.pointerId) return;
      const dx = event.clientX - start.x, dy = event.clientY - start.y;
      start = null;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.8) selectNation(selectedNation + (dx < 0 ? 1 : -1));
    }, { passive: true });
    stage.addEventListener('pointercancel', () => { start = null; }, { passive: true });
  }

  function refreshAnimations() {
    if (animationContext) { animationContext.revert(); animationContext = null; }
    if (!motion || !animationReady) return;
    animationContext = gsap.context(() => {
      if (!introPlayed && window.scrollY < 150) {
        introPlayed = true;
        gsap.timeline({ defaults: { ease: 'power3.out' } })
          .from('.hero-label', { opacity: 0, y: 10, duration: .65 }, .1)
          .from('.hero h1 .glyph', { yPercent: 110, rotationX: -65, opacity: 0, duration: 1.05, stagger: .035, ease: 'power4.out' }, .12)
          .from('.hero-under,.hero-actions', { opacity: 0, y: 18, duration: .8, stagger: .12 }, .65)
          .from('.hero-bottom,.hero-ball-caption', { opacity: 0, y: 12, duration: .8 }, .8);
      }
      gsap.utils.toArray('main h2').forEach((heading) => {
        gsap.from(heading.querySelectorAll('.word-rise'), {
          yPercent: 110, rotationX: -35, opacity: .1, duration: .95, stagger: .085, ease: 'power3.out',
          scrollTrigger: { trigger: heading, start: 'top 92%', once: true }
        });
      });
      gsap.utils.toArray('.editorial-card,.ticket,.edge-feature,.time-mark,.score-console').forEach((card, index) => {
        gsap.from(card, { opacity: 0, y: 24, duration: .7, delay: index % 3 * .055, ease: 'power2.out',
          scrollTrigger: { trigger: card, start: 'top 94%', once: true } });
      });
      gsap.utils.toArray('.competition').forEach((row) => {
        gsap.from(row, { opacity: 0, y: 13, duration: .55, ease: 'power2.out', scrollTrigger: { trigger: row, start: 'top 95%', once: true } });
      });
      gsap.utils.toArray('.editorial-photo,.about-photo,.ticket-photo,.feature-photo,.heritage-shot,.scoring-photo').forEach((frame) => {
        gsap.from(frame, { clipPath: 'inset(0 0 100% 0)', duration: 1.05, ease: 'power3.inOut',
          scrollTrigger: { trigger: frame, start: 'top 93%', once: true }, clearProps: 'clipPath' });
      });
      gsap.utils.toArray('.section-heading .kicker,.edge-copy>.kicker,.about-copy>.kicker').forEach((label) => {
        gsap.from(label, { x: -14, opacity: 0, duration: .7, ease: 'power2.out',
          scrollTrigger: { trigger: label, start: 'top 94%', once: true } });
      });
      gsap.from('.moment-tabs button', { y: 12, opacity: 0, duration: .55, stagger: .1,
        scrollTrigger: { trigger: '.moment-tabs', start: 'top 96%', once: true } });
      const media = gsap.matchMedia();

      media.add('(min-width: 1001px) and (pointer: fine)', () => {
        gsap.fromTo('.hero-art', { scale: 1.025, yPercent: 0 }, {
          scale: 1.09, yPercent: 4, ease: 'none',
          scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: .8 }
        });
        gsap.to('.hero-copy', { y: 42, opacity: .5, ease: 'none', scrollTrigger: { trigger: '.hero', start: '25% top', end: 'bottom top', scrub: .65 } });
        gsap.utils.toArray('.editorial-photo img,.heritage-shot img,.join-section>img,.section-photo-bg img').forEach((image) => {
          gsap.fromTo(image, { yPercent: -3, scale: 1.075 }, {
            yPercent: 3, scale: 1.075, ease: 'none',
            scrollTrigger: { trigger: image.parentElement, start: 'top bottom', end: 'bottom top', scrub: .8 }
          });
        });
        gsap.from('.edge-cinema', { y: 45, rotate: 1.4, duration: 1.1, ease: 'power3.out', scrollTrigger: { trigger: '.edge-cinema', start: 'top 88%', once: true } });
        // Restrained card depth follows a mouse or trackpad; touch layouts remain steady.
        const cleanups = [];
        document.querySelectorAll('.edge-cinema,.ticket').forEach((card) => {
          const rotateX = gsap.quickTo(card, 'rotationX', { duration: .6, ease: 'power2.out' });
          const rotateY = gsap.quickTo(card, 'rotationY', { duration: .6, ease: 'power2.out' });
          gsap.set(card, { transformPerspective: 1100 });
          const moveCard = (event) => {
            if (event.pointerType === 'touch') return;
            const box = card.getBoundingClientRect();
            rotateX((.5 - (event.clientY - box.top) / box.height) * 4);
            rotateY(((event.clientX - box.left) / box.width - .5) * 4);
          };
          const resetCard = () => { rotateX(0); rotateY(0); };
          card.addEventListener('pointermove', moveCard, { passive: true });
          card.addEventListener('pointerleave', resetCard, { passive: true });
          card.addEventListener('focusin', resetCard);
          cleanups.push(() => { card.removeEventListener('pointermove', moveCard); card.removeEventListener('pointerleave', resetCard); card.removeEventListener('focusin', resetCard); });
        });
        gsap.utils.toArray('.section-heading>p,.section-intro>p,.about-copy>p').forEach((copy) => {
          gsap.fromTo(copy, { opacity: .4, y: 14 }, { opacity: 1, y: 0, ease: 'none',
            scrollTrigger: { trigger: copy, start: 'top 88%', end: 'top 66%', scrub: .6 } });
        });
        const hero = $('hero');
        const lightX = gsap.quickTo('.hero-light', 'x', { duration: .8, ease: 'power2.out' });
        const lightY = gsap.quickTo('.hero-light', 'y', { duration: .8, ease: 'power2.out' });
        const move = (event) => {
          const box = hero.getBoundingClientRect();
          lightX(((event.clientX - box.left) / box.width - .5) * 35);
          lightY(((event.clientY - box.top) / box.height - .5) * 25);
        };
        const leave = () => { lightX(0); lightY(0); };
        hero.addEventListener('pointermove', move, { passive: true });
        hero.addEventListener('pointerleave', leave, { passive: true });
        return () => { hero.removeEventListener('pointermove', move); hero.removeEventListener('pointerleave', leave); cleanups.forEach((clean) => clean()); };
      });
      return () => media.revert();
    });
  }
  function applyMotion() {
    document.body.classList.toggle('motion-paused', !motion);
    refreshAnimations();
    if (!motion && animationReady) {
      const changing = document.querySelectorAll('.moment-panel>img,.moment-panel>figcaption,.nation-panel .glyph');
      gsap.killTweensOf(changing); gsap.set(changing, { clearProps: 'opacity,transform,clipPath' });
    }
  }
  reduced.addEventListener('change', () => { motion = !reduced.matches; applyMotion(); });
  document.addEventListener('visibilitychange', () => {
    document.body.classList.toggle('page-hidden', document.hidden);
  });
  // Real text stays in the source. Character wrappers keep whole words together.
  document.querySelectorAll('.hero h1,.nation-panel h3').forEach((heading) => {
    heading.setAttribute('aria-label', heading.innerText.replace(/\s+/g, ' ').trim());
    const walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      const fragment = document.createDocumentFragment();
      node.textContent.split(/(\s+)/).forEach((word) => {
        if (!word.trim()) { fragment.append(document.createTextNode(word)); return; }
        const wrapper = document.createElement('span'); wrapper.className = 'character-word'; wrapper.setAttribute('aria-hidden', 'true');
        [...word].forEach((letter) => { const glyph = document.createElement('span'); glyph.className = 'glyph'; glyph.textContent = letter; wrapper.append(glyph); });
        fragment.append(wrapper);
      });
      node.replaceWith(fragment);
    });
  });
  // Keep words intact when lines reflow; source text remains readable without GSAP.
  document.querySelectorAll('main h2').forEach((heading) => {
    heading.setAttribute('aria-label', heading.innerText.replace(/\s+/g, ' ').trim());
    const walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      const fragment = document.createDocumentFragment();
      node.textContent.split(/(\s+)/).forEach((word) => {
        if (!word.trim()) fragment.append(document.createTextNode(word));
        else {
          const clip = document.createElement('span'); clip.className = 'word-clip'; clip.setAttribute('aria-hidden', 'true');
          const inner = document.createElement('span'); inner.className = 'word-rise'; inner.textContent = word;
          clip.append(inner); fragment.append(clip);
        }
      });
      node.replaceWith(fragment);
    });
  });
  applyMotion();

  const moments = [...document.querySelectorAll('.moment-panel')];
  const momentTabs = [...document.querySelectorAll('[data-moment]')];
  let momentIndex = 0;
  function selectMoment(index, focus = false) {
    momentIndex = (index + moments.length) % moments.length;
    moments.forEach((panel, i) => {
      panel.hidden = i !== momentIndex;
      panel.inert = i !== momentIndex;
      momentTabs[i].setAttribute('aria-selected', String(i === momentIndex));
      momentTabs[i].tabIndex = i === momentIndex ? 0 : -1;
    });
    if (focus) momentTabs[momentIndex].focus({ preventScroll: true });
    const active = moments[momentIndex];
    if (animationReady) {
      gsap.killTweensOf(moments.flatMap((panel) => [...panel.children]));
      gsap.set(active.children, { clearProps: 'opacity,transform,clipPath' });
      if (motion) {
        gsap.fromTo(active.querySelector('img'), { scale: 1.08, clipPath: 'inset(0 0 0 100%)' }, { scale: 1, clipPath: 'inset(0 0 0 0%)', duration: .9, ease: 'power3.inOut', clearProps: 'transform,clipPath' });
        gsap.fromTo(active.querySelector('figcaption'), { opacity: 0, y: 17 }, { opacity: 1, y: 0, duration: .6, delay: .2, clearProps: 'opacity,transform' });
      }
    }
  }
  if (moments.length && moments.length === momentTabs.length) {
    document.querySelector('.moment-tabs').hidden = false;
    moments.forEach((panel, i) => { panel.inert = i !== 0; });
    momentTabs.forEach((tab, i) => {
      tab.addEventListener('click', () => { if (i !== momentIndex) selectMoment(i); });
      tab.addEventListener('keydown', (event) => {
        const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: moments.length - 1 }[event.key];
        if (next !== undefined) { event.preventDefault(); selectMoment(next, true); }
      });
    });
    const stage = document.querySelector('.moment-stage');
    let start = null;
    stage.addEventListener('pointerdown', (event) => { if (event.pointerType === 'touch') start = { x: event.clientX, y: event.clientY }; }, { passive: true });
    stage.addEventListener('pointerup', (event) => {
      if (!start) return;
      const dx = event.clientX - start.x, dy = event.clientY - start.y; start = null;
      if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.8) selectMoment(momentIndex + (dx < 0 ? 1 : -1));
    }, { passive: true });
    stage.addEventListener('pointercancel', () => { start = null; }, { passive: true });
  }

  const filterButtons = [...document.querySelectorAll('[data-competition-filter]')];
  const competitionRows = [...document.querySelectorAll('[data-competition]')];
  document.querySelector('.competition-tools').hidden = false;
  filterButtons.forEach((button) => button.addEventListener('click', () => {
    const value = button.dataset.competitionFilter;
    filterButtons.forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    competitionRows.forEach((row) => { row.hidden = value !== 'all' && row.dataset.competition !== value; });
    const visible = competitionRows.filter((row) => !row.hidden);
    $('competitionCount').textContent = `${visible.length} competitions`;
    if (animationReady) {
      gsap.killTweensOf(competitionRows);
      gsap.set(competitionRows, { clearProps: 'opacity,transform' });
      if (motion) gsap.fromTo(visible, { opacity: .25, y: 12 }, { opacity: 1, y: 0, duration: .4, stagger: .035, clearProps: 'opacity,transform', onComplete: () => ST.refresh() });
      else ST.refresh();
    }
  }));
  const features = [...document.querySelectorAll('.edge-feature')];
  features.forEach((feature) => feature.addEventListener('toggle', () => {
    if (!feature.open) return;
    features.forEach((other) => { if (other !== feature) other.open = false; });
    if (animationReady && motion) gsap.fromTo(feature.querySelector('.feature-detail'), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: .35, clearProps: 'opacity,transform' });
  }));

  const timeline = document.querySelector('.timeline-track');
  const earlier = $('historyPrev');
  const later = $('historyNext');
  if (timeline && earlier && later) {
    document.querySelector('.timeline-controls').hidden = false;
    const sync = () => {
      earlier.disabled = timeline.scrollLeft < 2;
      later.disabled = timeline.scrollLeft + timeline.clientWidth >= timeline.scrollWidth - 2;
    };
    const move = (direction) => timeline.scrollBy({ left: direction * Math.max(230, timeline.clientWidth * .7), behavior: motion ? 'smooth' : 'instant' });
    earlier.addEventListener('click', () => move(-1));
    later.addEventListener('click', () => move(1));
    timeline.addEventListener('scroll', sync, { passive: true });
    window.addEventListener('resize', sync, { passive: true });
    sync();
  }
  let progressFrame = 0;
  const progress = document.querySelector('.reading-progress i');
  function updateProgress() {
    progressFrame = 0;
    const total = document.documentElement.scrollHeight - innerHeight;
    const fraction = total > 0 ? Math.max(0, Math.min(1, scrollY / total)) : 0;
    progress.style.transform = `scaleX(${fraction})`;
  }
  window.addEventListener('scroll', () => {
    if (!progressFrame) progressFrame = requestAnimationFrame(updateProgress);
  }, { passive: true });
  window.addEventListener('resize', updateProgress, { passive: true });
  document.querySelectorAll('details').forEach((detail) => detail.addEventListener('toggle', () => {
    updateProgress();
    if (animationReady) requestAnimationFrame(() => ST.refresh());
  }));
  updateProgress();
  document.fonts?.ready.then(() => { if (animationReady) ST.refresh(); });
  window.addEventListener('load', () => { if (animationReady) ST.refresh(); }, { once: true });
})();
