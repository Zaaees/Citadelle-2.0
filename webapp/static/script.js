document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('draw-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const res = await fetch('/draw', { method: 'POST' });
        const data = await res.json();
        const container = document.getElementById('results');
        container.innerHTML = '';
        if (data.error) {
            container.textContent = data.error === 'already_drawn' ?
                'Tirage déjà effectué aujourd\'hui.' : 'Erreur.';
            return;
        }
        data.cards.forEach(card => {
            const div = document.createElement('div');
            div.className = 'card';
            div.innerHTML = `\n<div class="card-inner">\n  <div class="card-front">?\uD83C\uDCCF</div>\n  <div class="card-back"><strong>${card.name}</strong><br>${card.category}</div>\n</div>`;
            container.appendChild(div);
            setTimeout(() => div.classList.add('flip'), 100);
        });
    });
});
