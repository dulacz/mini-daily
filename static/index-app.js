document.addEventListener('alpine:init', () => {
    Alpine.data('wellnessApp', () => ({
        // Core state
        activities: [],
        config: null,
        taskIds: [],
        loading: true,
        error: null,
        serverDate: null, // Store server's current date

        // Display state
        streak: 0,
        totalStars365: 0,

        // Calendar state
        currentMonth: null,
        currentYear: null,
        calendarHtml: '',

        async init() {
            console.log('Initializing Wellness Tracker...');
            try {
                await this.loadConfig();
                await this.loadData();
                await this.updateStats();
                await this.renderCalendar();
                this.createParticles();
            } catch (error) {
                console.error('Initialization error:', error);
                this.error = 'Failed to load application: ' + error.message;
            } finally {
                this.loading = false;
            }
        },

        async loadConfig() {
            const response = await fetch('/api/config');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();
            this.config = data.user_configs.alice;

            // Store task IDs in order
            this.taskIds = Object.keys(this.config.tasks);

            // Build activities array
            this.activities = [];
            Object.keys(this.config.tasks).forEach(taskId => {
                const task = this.config.tasks[taskId];
                Object.keys(task.activities).forEach(activityId => {
                    this.activities.push({
                        key: `${taskId}_${activityId}`,
                        task: taskId,
                        activity: activityId,
                        label: task.activities[activityId].label,
                        link: task.activities[activityId].link || null,
                        taskTitle: task.title,
                        completed: false
                    });
                });
            });

            console.log('Config loaded, activities:', this.activities.length);
        },

        async loadData() {
            const response = await fetch('/api/day/completions');
            if (response.ok) {
                const data = await response.json();
                const completions = data.completions || {};
                const lastCompletions = data.last_completions || {};

                // Store server's date
                this.serverDate = data.date;

                // Initialize calendar to server's current month/year
                if (this.currentMonth === null) {
                    const serverDateObj = new Date(this.serverDate + 'T00:00:00');
                    this.currentMonth = serverDateObj.getMonth();
                    this.currentYear = serverDateObj.getFullYear();
                }

                // Update activity completion status and last completion date
                this.activities.forEach(activity => {
                    const taskCompletions = completions[activity.task] || {};
                    activity.completed = taskCompletions[activity.activity] || false;

                    const taskLastCompletions = lastCompletions[activity.task] || {};
                    activity.lastCompletedDate = taskLastCompletions[activity.activity] || null;
                });
            }
        },

        getTimeAgo(dateStr) {
            if (!dateStr) return 'Never';

            const date = new Date(dateStr + 'T00:00:00');
            const today = new Date(this.serverDate + 'T00:00:00');
            const diffTime = today - date;
            const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            if (diffDays < 14) return `${diffDays} days ago`;
            if (diffDays < 60) {
                const weeks = Math.floor(diffDays / 7);
                return weeks === 1 ? '1 week ago' : `${weeks} weeks ago`;
            }
            if (diffDays < 365) {
                const months = Math.floor(diffDays / 30);
                return months === 1 ? '1 month ago' : `${months} months ago`;
            }
            const years = Math.floor(diffDays / 365);
            return years === 1 ? '1 year ago' : `${years} years ago`;
        },

        async toggleActivity(task, activity) {
            const activityObj = this.activities.find(a => a.task === task && a.activity === activity);
            if (!activityObj) return;

            // Toggle completion
            activityObj.completed = !activityObj.completed;

            // Save to backend
            try {
                const response = await fetch('/api/activity/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task: task,
                        activity: activity,
                        completed: activityObj.completed
                    })
                });

                if (!response.ok) {
                    // Revert on error
                    activityObj.completed = !activityObj.completed;
                } else {
                    await this.updateStats();
                    await this.renderCalendar();
                }
            } catch (error) {
                console.error('Error saving activity:', error);
                // Revert on error
                activityObj.completed = !activityObj.completed;
            }
        },

        async updateStats() {
            try {
                const response = await fetch('/api/stats');
                if (response.ok) {
                    const stats = await response.json();
                    this.streak = stats.streak || 0;
                    this.totalStars365 = stats.total_stars_365 || 0;
                }
            } catch (error) {
                console.error('Error updating stats:', error);
            }
        },

        async renderCalendar() {
            try {
                const firstDay = new Date(this.currentYear, this.currentMonth, 1);
                const lastDay = new Date(this.currentYear, this.currentMonth + 1, 0);
                const daysInMonth = lastDay.getDate();
                const startingDayOfWeek = firstDay.getDay();

                const response = await fetch('/api/history?days=365');
                if (!response.ok) throw new Error('Failed to fetch history');

                const data = await response.json();
                const historyMap = data.history || {};

                // Use server's date instead of browser's local date
                const todayDateStr = this.serverDate;
                let html = '';

                const totalCells = Math.ceil((daysInMonth + startingDayOfWeek) / 7) * 7;

                for (let i = 0; i < totalCells; i++) {
                    const dayNumber = i - startingDayOfWeek + 1;

                    if (dayNumber <= 0 || dayNumber > daysInMonth) {
                        html += '<div class="day-cell outside-month"></div>';
                    } else {
                        const date = new Date(this.currentYear, this.currentMonth, dayNumber);
                        const dateStr = date.toISOString().split('T')[0];
                        const dayData = historyMap[dateStr];

                        let totalCompleted = 0;
                        if (dayData) {
                            // dayData is like {'duty': 9, 'fitness': 10, 'meaning': 8}
                            // Sum up all the completion counts
                            Object.values(dayData).forEach(count => {
                                if (typeof count === 'number') {
                                    totalCompleted += count;
                                }
                            });
                        }

                        let levelClass = 'level-0';
                        if (totalCompleted >= 3) levelClass = 'level-3';
                        else if (totalCompleted >= 2) levelClass = 'level-2';
                        else if (totalCompleted >= 1) levelClass = 'level-1';

                        const isToday = dateStr === todayDateStr ? 'today' : '';

                        html += `<div class="day-cell ${levelClass} ${isToday}">
                            <div class="day-number">${dayNumber}</div>
                            ${totalCompleted > 0 ? `<div class="day-stars">⭐${totalCompleted}</div>` : ''}
                        </div>`;
                    }
                }

                this.calendarHtml = html;
            } catch (error) {
                console.error('Error rendering calendar:', error);
                this.calendarHtml = '<div class="error-state">Failed to load calendar</div>';
            }
        },

        previousMonth() {
            if (this.currentMonth === 0) {
                this.currentMonth = 11;
                this.currentYear--;
            } else {
                this.currentMonth--;
            }
            this.renderCalendar();
        },

        nextMonth() {
            if (this.currentMonth === 11) {
                this.currentMonth = 0;
                this.currentYear++;
            } else {
                this.currentMonth++;
            }
            this.renderCalendar();
        },

        getTaskActivities(taskId) {
            return this.activities
                .filter(a => a.task === taskId)
                .sort((a, b) => {
                    // Null dates (never completed) come first
                    if (!a.lastCompletedDate && !b.lastCompletedDate) return 0;
                    if (!a.lastCompletedDate) return -1;
                    if (!b.lastCompletedDate) return 1;

                    // Otherwise sort by date (oldest first)
                    return new Date(a.lastCompletedDate) - new Date(b.lastCompletedDate);
                });
        },

        getTaskCompletedCount(taskId) {
            return this.activities.filter(a => a.task === taskId && a.completed).length;
        },

        getTaskActivityCount(taskId) {
            return this.activities.filter(a => a.task === taskId).length;
        },

        getTaskTitle(taskId) {
            if (!this.config || !this.config.tasks[taskId]) return taskId;
            const task = this.config.tasks[taskId];
            const icon = task.icon || '';
            const title = task.title || taskId;
            return icon ? `${icon} ${title}` : title;
        },

        get completedToday() {
            return this.activities.filter(a => a.completed).length;
        },

        get completionPercentage() {
            if (this.activities.length === 0) return 0;
            return (this.completedToday / this.activities.length) * 100;
        },

        get currentMonthDisplay() {
            const date = new Date(this.currentYear, this.currentMonth);
            return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        },

        // Particles animation - uses shared utility function
        createParticles() {
            const particlesContainer = this.$refs.particles;
            window.createParticles(particlesContainer, 30);
        }
    }));
});
