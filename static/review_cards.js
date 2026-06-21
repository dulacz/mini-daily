function reviewCardsApp() {
    return {
        loading: true,
        allCards: [],
        todayCards: [],
        categories: [],
        intervals: [],
        sortBy: 'next_review_date',
        sortDir: 'asc',
        newCard: { title: '', categoryInput: '' },

        async init() {
            await this.refresh();
            this.loading = false;
        },

        async refresh() {
            const [allResp, todayResp, catResp] = await Promise.all([
                fetch('/api/review_cards/all').then(r => r.json()),
                fetch('/api/review_cards/today').then(r => r.json()),
                fetch('/api/review_cards/categories').then(r => r.json()),
            ]);
            this.allCards = allResp.cards;
            this.intervals = allResp.intervals;
            this.todayCards = todayResp.cards;
            this.categories = catResp.categories;
        },

        get sortedAllCards() {
            const cards = [...this.allCards];
            const dir = this.sortDir === 'asc' ? 1 : -1;
            cards.sort((a, b) => {
                let cmp = 0;
                if (this.sortBy === 'category') {
                    cmp = a.category_name.localeCompare(b.category_name);
                    if (cmp === 0) cmp = a.next_review_date.localeCompare(b.next_review_date);
                } else {
                    cmp = a.next_review_date.localeCompare(b.next_review_date);
                    if (cmp === 0) cmp = a.category_name.localeCompare(b.category_name);
                }
                return cmp * dir;
            });
            return cards;
        },

        toggleSort(field) {
            if (this.sortBy === field) {
                this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortBy = field;
                this.sortDir = 'asc';
            }
        },

        todayStr() {
            // Use local date
            const d = new Date();
            return d.getFullYear() + '-' +
                String(d.getMonth() + 1).padStart(2, '0') + '-' +
                String(d.getDate()).padStart(2, '0');
        },

        isOverdue(card) {
            return !card.mastered && card.next_review_date && card.next_review_date < this.todayStr();
        },

        isToday(card) {
            return !card.mastered && card.next_review_date === this.todayStr();
        },

        formatDate(dateStr) {
            if (!dateStr) return '';
            const today = this.todayStr();
            if (dateStr === today) return 'Today';
            if (dateStr < today) {
                const diff = Math.round((new Date(today) - new Date(dateStr)) / 86400000);
                return `${diff}d overdue`;
            }
            const diff = Math.round((new Date(dateStr) - new Date(today)) / 86400000);
            if (diff === 1) return 'Tomorrow';
            return `in ${diff}d`;
        },

        progressClass(pct) {
            if (pct >= 100) return 'progress-complete';
            if (pct >= 60) return 'progress-good';
            if (pct >= 40) return 'progress-mid';
            return 'progress-low';
        },

        linkify(text) {
            const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
        },

        async createCard() {
            const title = this.newCard.title.trim();
            const categoryName = this.newCard.categoryInput.trim();
            if (!title || !categoryName) return;

            const resp = await fetch('/api/review_cards/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, category_name: categoryName }),
            });
            if (resp.ok) {
                this.newCard.title = '';
                this.newCard.categoryInput = '';
                await this.refresh();
            }
        },

        async reviewCard(cardId, difficulty) {
            const resp = await fetch('/api/review_cards/review', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ card_id: cardId, difficulty }),
            });
            if (resp.ok) {
                await this.refresh();
            }
        },

        async deleteCard(cardId) {
            if (!confirm('Delete this card?')) return;
            const resp = await fetch(`/api/review_cards/${cardId}`, { method: 'DELETE' });
            if (resp.ok) {
                await this.refresh();
            }
        },

        async renameCard(card) {
            const newTitle = prompt('Rename card:', card.title);
            if (newTitle === null || newTitle.trim() === '' || newTitle.trim() === card.title) return;
            const resp = await fetch('/api/review_cards/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ card_id: card.id, title: newTitle.trim() }),
            });
            if (resp.ok) {
                await this.refresh();
            }
        },
    };
}
