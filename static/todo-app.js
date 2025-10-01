/**
 * Alpine.js Todo Application for LeetCode Question Tracking
 * Groups questions by days and tracks completion status
 */

// Alpine.js component definition
function todoApp() {
    return {
        // Core state
        days: {},
        completedQuestions: new Set(),

        // UI state
        loading: true,
        error: null,
        currentDate: '',

        // Progress tracking
        circumference: 2 * Math.PI * 50, // for progress circle

        // Computed properties
        get sortedDays() {
            return Object.values(this.days).sort((a, b) => a.dayNumber - b.dayNumber);
        },

        get totalQuestions() {
            return Object.values(this.days).reduce((total, day) => total + day.total, 0);
        },

        get totalCompleted() {
            return this.completedQuestions.size;
        },

        get completedDays() {
            return Object.values(this.days).filter(day => day.isCompleted).length;
        },

        get progressPercentage() {
            if (this.totalQuestions === 0) return 0;
            return (this.totalCompleted / this.totalQuestions) * 100;
        },

        // Initialization
        async init() {
            this.currentDate = new Date().toLocaleDateString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });

            await this.loadQuestions();
            await this.loadCompletionStatus();
            this.updateDayStats();
            this.createParticles();
            this.loading = false;
        },

        // Data loading
        async loadQuestions() {
            try {
                const response = await fetch('/api/todo/questions');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                this.processQuestions(data.questions || []);
            } catch (error) {
                console.error('Error loading questions:', error);
                this.error = 'Failed to load questions. Please try again.';
            }
        },

        async loadCompletionStatus() {
            try {
                const response = await fetch('/api/todo/completed');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                const completed = data.completed || [];
                this.completedQuestions = new Set(completed);
            } catch (error) {
                console.error('Error loading completion status:', error);
                // Continue without completion status - not critical
            }
        },

        processQuestions(questions) {
            this.days = {};

            questions.forEach(question => {
                const dayNumber = parseInt(question.day);

                if (!this.days[dayNumber]) {
                    this.days[dayNumber] = {
                        dayNumber,
                        questions: [],
                        total: 0,
                        completed: 0,
                        isCompleted: false,
                        isCollapsed: false
                    };
                }

                // Use question_id from API response
                const questionId = question.question_id;

                this.days[dayNumber].questions.push({
                    id: questionId,
                    name: question.name,
                    difficulty: question.difficulty,
                    link: question.link,
                    topics: question.topics,
                    completed: false
                });

                this.days[dayNumber].total++;
            });
        },

        createQuestionId(name) {
            return name.toLowerCase()
                .replace(/[^a-z0-9\s]/g, '')
                .replace(/\s+/g, '-');
        },

        updateDayStats() {
            Object.values(this.days).forEach(day => {
                day.completed = day.questions.filter(q => this.completedQuestions.has(q.id)).length;
                day.isCompleted = day.completed === day.total && day.total > 0;

                // Auto-collapse completed days
                if (day.isCompleted && !day.isCollapsed) {
                    day.isCollapsed = true;
                }

                // Update question completion status
                day.questions.forEach(question => {
                    question.completed = this.completedQuestions.has(question.id);
                });
            });
        },

        // Day management
        toggleDay(dayNumber) {
            const day = this.days[dayNumber];
            if (day) {
                day.isCollapsed = !day.isCollapsed;
            }
        },

        // Question management
        async toggleQuestion(dayNumber, questionId) {
            try {
                const isCompleted = this.completedQuestions.has(questionId);
                const newStatus = !isCompleted;

                // Optimistically update UI
                if (newStatus) {
                    this.completedQuestions.add(questionId);
                } else {
                    this.completedQuestions.delete(questionId);
                }
                this.updateDayStats();

                // Send to backend
                const response = await fetch('/api/todo/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question_id: questionId,
                        completed: newStatus
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                if (!result.success) {
                    throw new Error('Failed to save completion status');
                }

            } catch (error) {
                console.error('Error toggling question:', error);

                // Revert optimistic update on error
                const isCompleted = this.completedQuestions.has(questionId);
                if (isCompleted) {
                    this.completedQuestions.delete(questionId);
                } else {
                    this.completedQuestions.add(questionId);
                }
                this.updateDayStats();

                // Show error to user
                this.error = 'Failed to save progress. Please try again.';
                setTimeout(() => {
                    this.error = null;
                }, 3000);
            }
        },

        // Particles animation
        createParticles() {
            const particlesContainer = this.$refs.particles;
            if (!particlesContainer) return;

            particlesContainer.innerHTML = '';

            for (let i = 0; i < 30; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.animationDelay = Math.random() * 20 + 's';
                particle.style.animationDuration = (Math.random() * 10 + 15) + 's';
                particlesContainer.appendChild(particle);
            }
        }
    }
}

// Make the function globally available for Alpine.js
window.todoApp = todoApp;