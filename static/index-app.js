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

        // Historical date navigation
        viewingDate: null, // null = today; set to a date string to view that day

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
                    const activityConfig = task.activities[activityId];
                    this.activities.push({
                        key: `${taskId}_${activityId}`,
                        task: taskId,
                        activity: activityId,
                        label: activityConfig.label,
                        link: activityConfig.link || null,
                        taskTitle: task.title,
                        completed: false,
                        intervalDays: activityConfig.interval_days || null,
                        colorRecent: task.color_recent || null,
                        colorOverdue: task.color_overdue || null,
                        streakBorder: task.streak_border !== false
                    });
                });
            });

            console.log('Config loaded, activities:', this.activities.length);
        },

        async loadData() {
            // Use viewingDate if set, otherwise fetch today's data
            const dateParam = this.viewingDate ? `?date_str=${this.viewingDate}` : '';
            const response = await fetch(`/api/day/completions${dateParam}`);
            if (response.ok) {
                const data = await response.json();
                const completions = data.completions || {};
                const lastCompletions = data.last_completions || {};
                const recentCounts = data.recent_counts || {};

                // Always store the server's true current date on first load
                if (!this.serverDate) {
                    this.serverDate = data.date;
                }

                // Initialize calendar to server's current month/year on first load
                if (this.currentMonth === null) {
                    const serverDateObj = new Date(this.serverDate + 'T00:00:00');
                    this.currentMonth = serverDateObj.getMonth();
                    this.currentYear = serverDateObj.getFullYear();
                }

                // Update activity completion status and last completion date.
                // Only activities present in the current config are updated —
                // deprecated DB entries are silently ignored.
                this.activities.forEach(activity => {
                    const taskCompletions = completions[activity.task] || {};
                    activity.completed = taskCompletions[activity.activity] || false;

                    const taskLastCompletions = lastCompletions[activity.task] || {};
                    activity.lastCompletedDate = taskLastCompletions[activity.activity] || null;
                    activity.recentCount = (recentCounts[activity.task] || {})[activity.activity] || 0;
                });
            }
        },

        /**
         * Load activity board for a specific historical date
         * @param {string} dateStr - ISO date string (YYYY-MM-DD)
         */
        async loadHistoricalDay(dateStr) {
            try {
                this.viewingDate = dateStr;
                await this.loadData();
                // Navigate calendar view to the month of the selected date
                const d = new Date(dateStr + 'T00:00:00');
                this.currentMonth = d.getMonth();
                this.currentYear = d.getFullYear();
                await this.renderCalendar();
                // Scroll to top of activity board
                const mainContent = document.querySelector('.main-content');
                if (mainContent) mainContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch (error) {
                console.error('Error loading historical day:', error);
            }
        },

        /**
         * Return to today's activities view
         */
        async returnToToday() {
            try {
                this.viewingDate = null;
                await this.loadData();
                // Navigate calendar back to current month
                const serverDateObj = new Date(this.serverDate + 'T00:00:00');
                this.currentMonth = serverDateObj.getMonth();
                this.currentYear = serverDateObj.getFullYear();
                await this.updateStats();
                await this.renderCalendar();
            } catch (error) {
                console.error('Error returning to today:', error);
            }
        },

        /**
         * Handle click on calendar grid (event delegation)
         * @param {MouseEvent} event
         */
        handleCalendarClick(event) {
            const cell = event.target.closest('[data-date]');
            if (!cell) return;
            const dateStr = cell.dataset.date;
            if (!dateStr) return;
            // Don't reload if already viewing this date
            const currentlyViewing = this.viewingDate || this.serverDate;
            if (dateStr === currentlyViewing) return;
            this.loadHistoricalDay(dateStr);
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

        /**
         * Get the color style for activity last completed text
         * @param {object} activity - Activity object
         * @returns {string} CSS color value or empty string
         */
        getActivityColor(activity) {
            if (!activity.intervalDays) return '';

            if (!activity.lastCompletedDate) {
                return activity.colorOverdue || '';
            }

            const date = new Date(activity.lastCompletedDate + 'T00:00:00');
            const today = new Date(this.serverDate + 'T00:00:00');
            const diffDays = Math.floor((today - date) / (1000 * 60 * 60 * 24));

            if (diffDays < activity.intervalDays / 2) {
                return activity.colorRecent || '';
            } else if (diffDays >= activity.intervalDays) {
                return activity.colorOverdue || '';
            }
            return '';
        },

        getActivityLabel(activity) {
            return activity.label;
        },

        getActivityStreakBorder(activity) {
            if (activity.streakBorder && activity.recentCount >= 2) return '#418a3e';
            return '';
        },

        async toggleActivity(task, activity) {
            const activityObj = this.activities.find(a => a.task === task && a.activity === activity);
            if (!activityObj) return;

            // Toggle completion
            activityObj.completed = !activityObj.completed;

            // Save to backend — include the viewing date so historical edits are stored correctly
            try {
                const body = {
                    task: task,
                    activity: activity,
                    completed: activityObj.completed
                };
                if (this.viewingDate) {
                    body.date = this.viewingDate;
                }

                const response = await fetch('/api/activity/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (!response.ok) {
                    // Revert on error
                    activityObj.completed = !activityObj.completed;
                } else {
                    // Only refresh stats when viewing today
                    if (!this.viewingDate) {
                        await this.updateStats();
                    }
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
                        const currentlyViewing = this.viewingDate || todayDateStr;
                        const isSelected = dateStr === currentlyViewing ? 'selected' : '';
                        // Only past and today dates are clickable (not future dates)
                        const isFuture = dateStr > todayDateStr;
                        const clickable = isFuture ? '' : 'clickable';

                        html += `<div class="day-cell ${levelClass} ${isToday} ${isSelected} ${clickable}" ${!isFuture ? `data-date="${dateStr}"` : ''}>
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
                    // Calculate due date (last completed + interval_days)
                    const getDueDate = (activity) => {
                        if (!activity.lastCompletedDate) return new Date('1900-01-01'); // Never completed = earliest
                        const lastDate = new Date(activity.lastCompletedDate + 'T00:00:00');
                        if (activity.intervalDays) {
                            lastDate.setDate(lastDate.getDate() + activity.intervalDays);
                        }
                        return lastDate;
                    };

                    // 0 = red (overdue), 1 = normal, 2 = green (recent)
                    const getColorPriority = (activity) => {
                        if (!activity.intervalDays) return 1;
                        if (!activity.lastCompletedDate) return 0;
                        const diffDays = Math.floor((new Date(this.serverDate + 'T00:00:00') - new Date(activity.lastCompletedDate + 'T00:00:00')) / (1000 * 60 * 60 * 24));
                        if (diffDays < activity.intervalDays / 2) return 2;
                        if (diffDays >= activity.intervalDays) return 0;
                        return 1;
                    };

                    const aPriority = getColorPriority(a);
                    const bPriority = getColorPriority(b);
                    if (aPriority !== bPriority) return aPriority - bPriority;

                    // Within same color group, sort by due date (earliest/most overdue first)
                    return getDueDate(a) - getDueDate(b);
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

        getTaskDescription(taskId) {
            if (!this.config || !this.config.tasks[taskId]) return '';
            const task = this.config.tasks[taskId];
            return task.description || '';
        },

        get isViewingHistorical() {
            return this.viewingDate !== null && this.viewingDate !== this.serverDate;
        },

        get viewingDateDisplay() {
            const d = this.viewingDate || this.serverDate;
            if (!d) return '';
            return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
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
