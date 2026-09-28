/**
 * Responsive mobile navigation menu toggle and accessibility handler.
 */
document.addEventListener('DOMContentLoaded', () => {
    const menuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');
    const hamburgerIcon = document.getElementById('hamburger-icon');
    const closeIcon = document.getElementById('close-icon');

    if (!menuButton || !mobileMenu) return;

    function toggleMenu(forceOpen) {
        const isCurrentlyOpen = !mobileMenu.classList.contains('hidden');
        const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !isCurrentlyOpen;

        if (shouldOpen) {
            mobileMenu.classList.remove('hidden');
            menuButton.setAttribute('aria-expanded', 'true');
            if (hamburgerIcon) hamburgerIcon.classList.add('hidden');
            if (closeIcon) closeIcon.classList.remove('hidden');
        } else {
            mobileMenu.classList.add('hidden');
            menuButton.setAttribute('aria-expanded', 'false');
            if (hamburgerIcon) hamburgerIcon.classList.remove('hidden');
            if (closeIcon) closeIcon.classList.add('hidden');
        }
    }

    menuButton.addEventListener('click', () => {
        toggleMenu();
    });

    // Close menu on Escape key for keyboard accessibility
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !mobileMenu.classList.contains('hidden')) {
            toggleMenu(false);
            menuButton.focus();
        }
    });

    // Close menu when viewport resizes to desktop breakpoint (md = 768px)
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 768 && !mobileMenu.classList.contains('hidden')) {
            toggleMenu(false);
        }
    });
});
