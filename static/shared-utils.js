/**
 * Shared utility functions for the Mini Daily application
 */

/**
 * Creates animated background particles
 * @param {HTMLElement} particlesContainer - The container element to add particles to
 * @param {number} count - Number of particles to create (default: 30)
 */
function createParticles(particlesContainer, count = 30) {
    if (!particlesContainer) {
        console.warn('Particles container not found');
        return;
    }

    particlesContainer.innerHTML = '';

    for (let i = 0; i < count; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDelay = Math.random() * 20 + 's';
        particle.style.animationDuration = (Math.random() * 10 + 15) + 's';
        particlesContainer.appendChild(particle);
    }
}

// Make function globally available
window.createParticles = createParticles;
