/* Rugby AI — shared behaviour for legal / content pages.
   Requires (loaded before this file): GSAP, ScrollTrigger, Lenis. All optional — degrades gracefully. */
(function () {
    'use strict';
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const doc = document;

    /* inject helper elements so the HTML pages stay clean */
    const grain = doc.createElement('div'); grain.className = 'grain'; doc.body.appendChild(grain);
    const progress = doc.createElement('div'); progress.id = 'readProgress'; doc.body.appendChild(progress);
    const toTop = doc.createElement('button'); toTop.id = 'toTop'; toTop.setAttribute('aria-label', 'Back to top'); toTop.innerHTML = '&#8593;'; doc.body.appendChild(toTop);

    /* mobile nav toggle */
    const navbar = doc.querySelector('.navbar');
    const navLinks = doc.querySelector('.nav-links');
    if (navbar && navLinks && !doc.querySelector('.nav-toggle')) {
        const btn = doc.createElement('button');
        btn.className = 'nav-toggle'; btn.setAttribute('aria-label', 'Menu'); btn.innerHTML = '&#9776;';
        navbar.insertBefore(btn, navLinks);
        btn.addEventListener('click', () => navLinks.classList.toggle('open'));
        navLinks.querySelectorAll('a').forEach(a => a.addEventListener('click', () => navLinks.classList.remove('open')));
    }

    /* highlight the active nav link for the current page */
    const here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
    doc.querySelectorAll('.nav-links a').forEach(a => {
        const href = (a.getAttribute('href') || '').toLowerCase();
        if (href === here) a.classList.add('active');
    });

    /* tag content blocks for reveal animation */
    const revealEls = [...doc.querySelectorAll('.section, .highlight-box, .last-updated')];
    revealEls.forEach(el => el.classList.add('reveal'));

    /* Lenis smooth scroll */
    let lenis = null;
    if (!reduceMotion && window.Lenis) {
        lenis = new window.Lenis({ lerp: 0.085, wheelMultiplier: 1.05, smoothWheel: true });
        if (window.gsap && window.gsap.ticker) {
            window.gsap.ticker.add((t) => lenis.raf(t * 1000));
            window.gsap.ticker.lagSmoothing(0);
        } else {
            const raf = (t) => { lenis.raf(t); requestAnimationFrame(raf); };
            requestAnimationFrame(raf);
        }
    }

    /* GSAP reveals + hero intro */
    if (window.gsap && window.ScrollTrigger) {
        const gsap = window.gsap; gsap.registerPlugin(window.ScrollTrigger);
        if (lenis) lenis.on('scroll', window.ScrollTrigger.update);

        revealEls.forEach(el => window.ScrollTrigger.create({ trigger: el, start: 'top 90%', onEnter: () => el.classList.add('in') }));

        const heroBits = doc.querySelectorAll('.hero h1, .hero .tagline');
        if (heroBits.length) gsap.from(heroBits, { y: 36, opacity: 0, duration: 1, ease: 'power3.out', stagger: .12, delay: .25 });
    } else {
        revealEls.forEach(el => el.classList.add('in'));
    }

    /* navbar shrink + reading progress + back-to-top */
    function onScroll() {
        const y = window.scrollY || doc.documentElement.scrollTop;
        if (navbar) navbar.classList.toggle('shrink', y > 40);
        const h = doc.documentElement.scrollHeight - innerHeight;
        progress.style.width = (h > 0 ? (y / h) * 100 : 0) + '%';
        toTop.classList.toggle('show', y > 600);
    }
    addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    toTop.addEventListener('click', () => { if (lenis) lenis.scrollTo(0, { duration: 1.1 }); else scrollTo({ top: 0, behavior: 'smooth' }); });
})();
