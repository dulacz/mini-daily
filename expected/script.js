'use strict';

/**
 * Daily Wellness Tracker Application
 * Manages task completion, streaks, and progress tracking
 */
class WellnessTracker {
    constructor() {
        this.tasks = ['reading', 'exercise', 'caring'];
        this.taskData = this.loadData();
        this.achievements = [
            { id: 'first_star', title: 'Getting Started!', message: 'You earned your first star today!', triggered: false },
            { id: 'all_tasks', title: 'Perfect Day!', message: 'You completed all three wellness tasks today!', triggered: false },
            { id: 'week_streak', title: 'Week Warrior!', message: 'You maintained a 7-day streak!', triggered: false },
            { id: 'month_streak', title: 'Monthly Master!', message: '30 days of consistency - amazing!', triggered: false }
        ];
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        try {
            this.setupEventListeners();
            this.updateDisplay();
            this.checkNewDay();
        } catch (error) {
            console.error('Error initializing wellness tracker:', error);
        }
    }

    /**
     * Load data from localStorage
     * @returns {Object} Task data object
     */
    loadData() {
        try {
            if (typeof Storage === 'undefined') {
                console.warn('localStorage not available, using session data');
                return this.getDefaultData();
            }

            const saved = localStorage.getItem('wellnessTrackerData');
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (error) {
            console.error('Error loading data from localStorage:', error);
        }
        return this.getDefaultData();
    }

    /**
     * Get default data structure
     * @returns {Object} Default task data
     */
    getDefaultData() {
        const today = this.getDateString();
        return {
            currentDate: today,
            daily: {
                [today]: {
                    reading: 0,
                    exercise: 0,
                    caring: 0,
                    completed: []
                }
            },
            streaks: {
                reading: 0,
                exercise: 0,
                caring: 0,
                overall: 0
            },
            achievements: []
        };
    }

    /**
     * Save data to localStorage
     */
    saveData() {
        try {
            if (typeof Storage !== 'undefined') {
                localStorage.setItem('wellnessTrackerData', JSON.stringify(this.taskData));
            }
        } catch (error) {
            console.error('Error saving data to localStorage:', error);
        }
    }

    /**
     * Get today's date as string
     * @returns {string} Date string in YYYY-MM-DD format
     */
    getDateString(date = new Date()) {
        return date.toISOString().split('T')[0];
    }

    /**
     * Check if it's a new day and reset if needed
     */
    checkNewDay() {
        const today = this.getDateString();
        if (this.taskData.currentDate !== today) {
            this.startNewDay(today);
        }
    }

    /**
     * Start a new day
     * @param {string} today - Today's date string
     */
    startNewDay(today) {
        // Calculate streaks before resetting
        this.updateStreaks();

        // Create new day entry
        this.taskData.daily[today] = {
            reading: 0,
            exercise: 0,
            caring: 0,
            completed: []
        };

        this.taskData.currentDate = today;
        this.saveData();
        this.updateDisplay();
    }

    /**
     * Update streak counters
     */
    updateStreaks() {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = this.getDateString(yesterday);

        if (this.taskData.daily[yesterdayStr]) {
            const yesterdayData = this.taskData.daily[yesterdayStr];

            // Update individual task streaks
            this.tasks.forEach(task => {
                if (yesterdayData[task] > 0) {
                    this.taskData.streaks[task]++;
                } else {
                    this.taskData.streaks[task] = 0;
                }
            });

            // Update overall streak (if at least 2 out of 3 tasks were done)
            const completedCount = this.tasks.reduce((count, task) => {
                return count + (yesterdayData[task] > 0 ? 1 : 0);
            }, 0);

            if (completedCount >= 2) {
                this.taskData.streaks.overall++;
            } else {
                this.taskData.streaks.overall = 0;
            }
        }
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Star button clicks
        document.querySelectorAll('.star-btn').forEach(btn => {
            btn.addEventListener('click', this.handleStarClick.bind(this));
        });

        // Weekly summary toggle
        const summaryToggle = document.getElementById('summaryToggle');
        if (summaryToggle) {
            summaryToggle.addEventListener('click', this.toggleWeeklySummary.bind(this));
        }

        // Achievement popup close (click anywhere)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.achievements')) {
                this.hideAchievement();
            }
        });
    }

    /**
     * Handle star button clicks
     * @param {Event} event - Click event
     */
    handleStarClick(event) {
        const btn = event.currentTarget;
        const task = btn.closest('.star-rating').dataset.task;
        const level = parseInt(btn.dataset.level);

        this.setTaskLevel(task, level);
    }

    /**
     * Set task completion level
     * @param {string} task - Task name
     * @param {number} level - Completion level (1-3)
     */
    setTaskLevel(task, level) {
        const today = this.getDateString();
        const currentLevel = this.taskData.daily[today][task];

        // Toggle behavior: if clicking the same level, set to 0, otherwise set to clicked level
        const newLevel = currentLevel === level ? 0 : level;

        this.taskData.daily[today][task] = newLevel;

        // Update completed tasks array
        const completedTasks = this.taskData.daily[today].completed;
        if (newLevel > 0 && !completedTasks.includes(task)) {
            completedTasks.push(task);
        } else if (newLevel === 0) {
            const index = completedTasks.indexOf(task);
            if (index > -1) {
                completedTasks.splice(index, 1);
            }
        }

        this.saveData();
        this.updateDisplay();
        this.checkAchievements();

        // Add visual feedback
        this.addCompletionFeedback(task, newLevel);
    }

    /**
     * Add visual feedback for task completion
     * @param {string} task - Task name
     * @param {number} level - Completion level
     */
    addCompletionFeedback(task, level) {
        const taskCard = document.querySelector(`[data-task="${task}"]`);
        if (!taskCard) return;

        // Add completion class temporarily
        if (level > 0) {
            taskCard.classList.add('completed');

            // Add a subtle shake animation
            taskCard.style.animation = 'none';
            setTimeout(() => {
                taskCard.style.animation = 'subtle-shake 0.5s ease-in-out';
            }, 10);
        } else {
            taskCard.classList.remove('completed');
        }
    }

    /**
     * Update all display elements
     */
    updateDisplay() {
        this.updateDateDisplay();
        this.updateProgressCircle();
        this.updateStats();
        this.updateTaskCards();
        this.updateStreakDisplay();
        this.updateWeeklySummary();
    }

    /**
     * Update date display
     */
    updateDateDisplay() {
        const dateElement = document.getElementById('dateDisplay');
        if (dateElement) {
            const today = new Date();
            const options = {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            };
            dateElement.textContent = today.toLocaleDateString('en-US', options);
        }
    }

    /**
     * Update progress circle
     */
    updateProgressCircle() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        const totalStars = Object.values(todayData).reduce((sum, val) => {
            return sum + (typeof val === 'number' ? val : 0);
        }, 0);

        const maxStars = this.tasks.length * 3; // 3 stars per task
        const percentage = Math.round((totalStars / maxStars) * 100);

        const progressCircle = document.getElementById('progressCircle');
        const progressPercentage = document.getElementById('progressPercentage');

        if (progressCircle && progressPercentage) {
            const circumference = 2 * Math.PI * 50; // radius = 50
            const offset = circumference - (percentage / 100) * circumference;

            progressCircle.style.strokeDashoffset = offset;
            progressPercentage.textContent = `${percentage}%`;
        }
    }

    /**
     * Update stats display
     */
    updateStats() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        const totalStars = Object.values(todayData).reduce((sum, val) => {
            return sum + (typeof val === 'number' ? val : 0);
        }, 0);

        const completedTasks = todayData.completed.length;

        const totalStarsElement = document.getElementById('totalStars');
        const completedTasksElement = document.getElementById('completedTasks');

        if (totalStarsElement) totalStarsElement.textContent = totalStars;
        if (completedTasksElement) completedTasksElement.textContent = completedTasks;
    }

    /**
     * Update task cards display
     */
    updateTaskCards() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        this.tasks.forEach(task => {
            const taskLevel = todayData[task];
            const taskCard = document.querySelector(`[data-task="${task}"]`);
            const starRating = document.querySelector(`[data-task="${task}"] .star-rating`);
            const taskBadge = document.getElementById(`${task}Badge`);
            const taskStreak = document.getElementById(`${task}Streak`);

            if (starRating) {
                // Update star buttons
                starRating.querySelectorAll('.star-btn').forEach((btn, index) => {
                    const btnLevel = index + 1;
                    if (btnLevel <= taskLevel) {
                        btn.classList.add('active');
                    } else {
                        btn.classList.remove('active');
                    }
                });
            }

            if (taskBadge) {
                // Update badge
                if (taskLevel === 0) {
                    taskBadge.textContent = 'Not Started';
                    taskBadge.className = 'task-badge';
                } else if (taskLevel < 3) {
                    taskBadge.textContent = 'In Progress';
                    taskBadge.className = 'task-badge started';
                } else {
                    taskBadge.textContent = 'Completed';
                    taskBadge.className = 'task-badge completed';
                }
            }

            if (taskStreak) {
                taskStreak.textContent = this.taskData.streaks[task] || 0;
            }

            // Update card completion state
            if (taskCard) {
                if (taskLevel > 0) {
                    taskCard.classList.add('completed');
                } else {
                    taskCard.classList.remove('completed');
                }
            }
        });
    }

    /**
     * Update streak display
     */
    updateStreakDisplay() {
        const streakCount = document.getElementById('streakCount');
        if (streakCount) {
            streakCount.textContent = this.taskData.streaks.overall || 0;
        }
    }

    /**
     * Check and trigger achievements
     */
    checkAchievements() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        // First star achievement
        const totalStars = Object.values(todayData).reduce((sum, val) => {
            return sum + (typeof val === 'number' ? val : 0);
        }, 0);

        if (totalStars > 0 && !this.taskData.achievements.includes('first_star')) {
            this.triggerAchievement('first_star');
        }

        // All tasks completed achievement
        if (todayData.completed.length === 3 && !this.taskData.achievements.includes('all_tasks')) {
            this.triggerAchievement('all_tasks');
        }

        // Streak achievements
        if (this.taskData.streaks.overall >= 7 && !this.taskData.achievements.includes('week_streak')) {
            this.triggerAchievement('week_streak');
        }

        if (this.taskData.streaks.overall >= 30 && !this.taskData.achievements.includes('month_streak')) {
            this.triggerAchievement('month_streak');
        }
    }

    /**
     * Trigger an achievement
     * @param {string} achievementId - Achievement ID
     */
    triggerAchievement(achievementId) {
        const achievement = this.achievements.find(a => a.id === achievementId);
        if (achievement && !this.taskData.achievements.includes(achievementId)) {
            this.taskData.achievements.push(achievementId);
            this.saveData();
            this.showAchievement(achievement);
        }
    }

    /**
     * Show achievement popup
     * @param {Object} achievement - Achievement object
     */
    showAchievement(achievement) {
        const achievementSection = document.getElementById('achievementsSection');
        const achievementTitle = document.getElementById('achievementTitle');
        const achievementMessage = document.getElementById('achievementMessage');

        if (achievementSection && achievementTitle && achievementMessage) {
            achievementTitle.textContent = achievement.title;
            achievementMessage.textContent = achievement.message;

            achievementSection.style.display = 'flex';
            setTimeout(() => {
                achievementSection.classList.add('show');
            }, 10);

            // Auto-hide after 4 seconds
            setTimeout(() => {
                this.hideAchievement();
            }, 4000);
        }
    }

    /**
     * Hide achievement popup
     */
    hideAchievement() {
        const achievementSection = document.getElementById('achievementsSection');
        if (achievementSection) {
            achievementSection.classList.remove('show');
            setTimeout(() => {
                achievementSection.style.display = 'none';
            }, 300);
        }
    }

    /**
     * Toggle weekly summary display
     */
    toggleWeeklySummary() {
        const summaryContent = document.getElementById('summaryContent');
        const summaryToggle = document.getElementById('summaryToggle');

        if (summaryContent && summaryToggle) {
            const isVisible = summaryContent.style.display !== 'none';

            if (isVisible) {
                summaryContent.style.display = 'none';
                summaryToggle.classList.remove('active');
            } else {
                summaryContent.style.display = 'block';
                summaryToggle.classList.add('active');
                this.renderWeeklyGrid();
            }
        }
    }

    /**
     * Update weekly summary
     */
    updateWeeklySummary() {
        // This will be called when the summary is toggled open
    }

    /**
     * Render weekly progress grid
     */
    renderWeeklyGrid() {
        const weeklyGrid = document.getElementById('weeklyGrid');
        if (!weeklyGrid) return;

        weeklyGrid.innerHTML = '';

        // Get last 7 days
        const today = new Date();
        const days = [];

        for (let i = 6; i >= 0; i--) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            days.push(date);
        }

        days.forEach(date => {
            const dateStr = this.getDateString(date);
            const dayData = this.taskData.daily[dateStr];

            const dayCell = document.createElement('div');
            dayCell.className = 'day-cell';

            const dayLabel = document.createElement('div');
            dayLabel.textContent = date.getDate();
            dayLabel.style.fontSize = '0.75rem';
            dayLabel.style.fontWeight = '600';

            const dayName = document.createElement('div');
            dayName.textContent = date.toLocaleDateString('en-US', { weekday: 'short' });
            dayName.style.fontSize = '0.625rem';
            dayName.style.opacity = '0.8';

            if (dayData) {
                const totalStars = Object.values(dayData).reduce((sum, val) => {
                    return sum + (typeof val === 'number' ? val : 0);
                }, 0);

                if (totalStars >= 9) { // All stars
                    dayCell.classList.add('completed');
                } else if (totalStars > 0) {
                    dayCell.classList.add('partial');
                }

                const starsDiv = document.createElement('div');
                starsDiv.textContent = `${totalStars}/9`;
                starsDiv.style.fontSize = '0.625rem';
                starsDiv.style.marginTop = '0.125rem';

                dayCell.appendChild(dayName);
                dayCell.appendChild(dayLabel);
                dayCell.appendChild(starsDiv);
            } else {
                dayCell.appendChild(dayName);
                dayCell.appendChild(dayLabel);
            }

            weeklyGrid.appendChild(dayCell);
        });
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    try {
        new WellnessTracker();
    } catch (error) {
        console.error('Failed to initialize Wellness Tracker:', error);
    }
});

// Add subtle shake animation to CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes subtle-shake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-2px); }
        75% { transform: translateX(2px); }
    }
`;
document.head.appendChild(style);