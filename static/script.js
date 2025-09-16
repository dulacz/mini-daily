'use strict';

/**
 * Daily Wellness Tracker Application
 * Manages task completion, streaks, and progress tracking
 */
class WellnessTracker {
    constructor() {
        this.tasks = []; // Will be loaded from backend
        this.taskLevels = {}; // Will be loaded from backend
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
    async init() {
        try {
            // Load configuration from backend first
            await this.loadConfig();

            await this.checkNewDay();
            this.setupEventListeners();
            this.updateDisplay();

            // Sync with backend on startup
            await this.syncWithBackend();
        } catch (error) {
            console.error('Error initializing WellnessTracker:', error);
        }
    }

    /**
     * Load configuration from backend
     */
    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const config = await response.json();
                this.taskLevels = config.task_levels || {}; // fallback
                // Derive tasks from task_levels keys
                this.tasks = Object.keys(this.taskLevels).length > 0 ?
                    Object.keys(this.taskLevels) :
                    ['reading', 'exercise', 'caring']; // fallback
                console.log('Loaded config:', config);

                // Generate task cards after loading config
                this.generateTaskCards();
            } else {
                throw new Error('Failed to load config');
            }
        } catch (error) {
            console.error('Error loading config, using defaults:', error);
            // Use fallback values if config loading fails
            this.tasks = ['reading', 'exercise', 'caring'];
            this.taskLevels = {};
            this.generateTaskCards(); // Generate with fallback data
        }
    }

    /**
     * Generate task cards dynamically from configuration
     */
    generateTaskCards() {
        const tasksContainer = document.getElementById('tasksContainer');
        if (!tasksContainer) return;

        tasksContainer.innerHTML = ''; // Clear existing content

        this.tasks.forEach(taskId => {
            const taskConfig = this.taskLevels[taskId];
            const taskCard = document.createElement('div');
            taskCard.className = 'task-card';
            taskCard.setAttribute('data-task', taskId);

            // Fallback values if config is missing
            const title = taskConfig?.title || this.capitalizeFirst(taskId);
            const icon = taskConfig?.icon || '⭐';
            const description = taskConfig?.description || `Complete your ${taskId} task`;
            const levels = taskConfig?.levels || { 1: "Level 1", 2: "Level 2", 3: "Level 3" };

            taskCard.innerHTML = `
                <div class="task-header">
                    <div class="task-icon">${icon}</div>
                    <h3 class="task-title">${title}</h3>
                    <div class="task-badge" id="${taskId}Badge">Not Started</div>
                </div>
                <div class="task-description">
                    <span class="task-desc-text">${description}</span>
                </div>
                <div class="star-rating" data-task="${taskId}">
                    ${Object.entries(levels).map(([level, desc]) => `
                        <button class="star-btn" data-level="${level}" title="${desc}">
                            <span class="star-icon">⭐</span>
                            <span class="star-label">${desc}</span>
                        </button>
                    `).join('')}
                </div>
            `;

            tasksContainer.appendChild(taskCard);
        });

        // Re-setup event listeners for the new buttons
        this.setupTaskEventListeners();
    }

    /**
     * Helper to capitalize first letter
     */
    capitalizeFirst(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    /**
     * Sync local data with backend
     */
    async syncWithBackend() {
        try {
            const response = await fetch('/api/status/today');
            if (response.ok) {
                const data = await response.json();
                const today = this.getDateString();

                // Update today's data with backend data
                if (data.status) {
                    this.taskData.daily[today] = {
                        ...this.taskData.daily[today],
                        ...data.status,
                        completed: []
                    };

                    // Rebuild completed array based on levels
                    Object.keys(data.status).forEach(task => {
                        if (data.status[task] > 0) {
                            this.taskData.daily[today].completed.push(task);
                        }
                    });

                    this.saveData();
                    await this.updateDisplay();
                }
            }
        } catch (error) {
            console.error('Error syncing with backend:', error);
            // Continue with local data if backend is unavailable
        }
    }

    /**
     * Load data from localStorage
     * @returns {Object} Task data object
     */
    loadData() {
        try {
            if (typeof Storage !== "undefined" && localStorage.getItem('wellnessData')) {
                const data = JSON.parse(localStorage.getItem('wellnessData'));
                // Ensure data has the right structure
                if (data && data.currentDate && data.daily && data.streaks) {
                    return data;
                }
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
            if (typeof Storage !== "undefined") {
                localStorage.setItem('wellnessData', JSON.stringify(this.taskData));
            }
        } catch (error) {
            console.error('Error saving data to localStorage:', error);
        }
    }

    /**
     * Get today's date as string in Pacific Time
     * @returns {string} Date string in YYYY-MM-DD format
     */
    getDateString(date = new Date()) {
        // Get the date string directly in Pacific Time
        const pacificDateParts = new Intl.DateTimeFormat('en-CA', {
            timeZone: 'America/Los_Angeles',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        }).formatToParts(date);

        const year = pacificDateParts.find(part => part.type === 'year').value;
        const month = pacificDateParts.find(part => part.type === 'month').value;
        const day = pacificDateParts.find(part => part.type === 'day').value;

        return `${year}-${month}-${day}`;
    }

    /**
     * Get current date in Pacific Time
     * @returns {Date} Date object representing current time in Pacific Time
     */
    getPacificDate() {
        const now = new Date();
        return new Date(now.toLocaleString("en-US", { timeZone: "America/Los_Angeles" }));
    }

    /**
     * Check if it's a new day and reset if needed
     */
    async checkNewDay() {
        const today = this.getDateString();
        if (this.taskData.currentDate !== today) {
            await this.startNewDay(today);
        }
    }

    /**
     * Start a new day
     * @param {string} today - Today's date string
     */
    async startNewDay(today) {
        // Calculate streaks before resetting
        await this.updateStreaks();

        // Create new day entry
        this.taskData.daily[today] = {
            reading: 0,
            exercise: 0,
            caring: 0,
            completed: []
        };

        this.taskData.currentDate = today;
        this.saveData();
        await this.updateDisplay();
    }

    /**
     * Update streak counters using recursive calculation
     */
    async updateStreaks() {
        // Calculate the true streak by counting backwards through history
        this.taskData.streaks.overall = await this.calculateTrueStreak();
    }

    /**
     * Calculate the actual streak by checking backwards through history
     */
    async calculateTrueStreak() {
        try {
            // Fetch historical data from backend
            const response = await fetch('/api/history?days=365');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const history = data.history;

            let streakCount = 0;
            const today = new Date();

            // Start from yesterday and work backwards
            for (let i = 1; i <= 365; i++) {
                const checkDate = new Date(today);
                checkDate.setDate(today.getDate() - i);
                const checkDateStr = this.getDateString(checkDate);

                const dayData = history[checkDateStr];

                // If no data for this day, stop counting
                if (!dayData) {
                    break;
                }

                // Check if all tasks were completed that day
                const allTasksCompleted = this.tasks.every(task =>
                    dayData[task] > 0
                );

                if (allTasksCompleted) {
                    streakCount++;
                } else {
                    // Found a day without all tasks completed, stop counting
                    break;
                }
            }

            return streakCount;
        } catch (error) {
            console.error('Error calculating streak from backend:', error);
            // Fallback to localStorage data
            return this.calculateTrueStreakFromLocal();
        }
    }

    /**
     * Fallback method to calculate streak from localStorage (limited data)
     */
    calculateTrueStreakFromLocal() {
        let streakCount = 0;
        const today = new Date();

        // Start from yesterday and work backwards
        for (let i = 1; i <= 365; i++) {
            const checkDate = new Date(today);
            checkDate.setDate(today.getDate() - i);
            const checkDateStr = this.getDateString(checkDate);

            const dayData = this.taskData.daily[checkDateStr];

            // If no data for this day, stop counting
            if (!dayData) {
                break;
            }

            // Check if all tasks were completed that day
            const allTasksCompleted = this.tasks.every(task =>
                dayData[task] > 0
            );

            if (allTasksCompleted) {
                streakCount++;
            } else {
                // Found a day without all tasks completed, stop counting
                break;
            }
        }

        return streakCount;
    }

    /**
     * Manually recalculate and update streak (useful for testing/debugging)
     */
    async recalculateStreak() {
        await this.updateStreaks();
        await this.updateStreakDisplay();
        this.saveData();
        console.log('Streak recalculated:', this.taskData.streaks.overall);
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Setup task-specific listeners (will be called after task cards are generated)
        this.setupTaskEventListeners();

        // Weekly summary toggle
        const summaryToggle = document.getElementById('summaryToggle');
        if (summaryToggle) {
            summaryToggle.addEventListener('click', () => this.toggleWeeklySummary());
        }

        // Achievement popup close (click anywhere)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.achievements')) {
                this.hideAchievement();
            }
        });
    }

    /**
     * Setup task-specific event listeners (called after task cards are generated)
     */
    setupTaskEventListeners() {
        // Star button clicks
        document.querySelectorAll('.star-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleStarClick(e));
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
    async setTaskLevel(task, level) {
        const today = this.getDateString();
        const currentLevel = this.taskData.daily[today][task];

        // Toggle behavior: if clicking the same level, set to 0, otherwise set to clicked level
        const newLevel = currentLevel === level ? 0 : level;

        try {
            // Call backend API to update database
            const response = await fetch('/api/task/level', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task: task,
                    level: newLevel
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            if (result.success) {
                // Update local data with server response
                this.taskData.daily[today][task] = newLevel;

                // Update completed tasks array
                const completedTasks = this.taskData.daily[today].completed;
                if (newLevel > 0 && !completedTasks.includes(task)) {
                    completedTasks.push(task);
                } else if (newLevel === 0 && completedTasks.includes(task)) {
                    const index = completedTasks.indexOf(task);
                    if (index > -1) {
                        completedTasks.splice(index, 1);
                    }
                }

                this.saveData();
                await this.updateDisplay();
                this.checkAchievements();

                // Add visual feedback
                this.addCompletionFeedback(task, newLevel);
            } else {
                console.error('Failed to update task level:', result.error);
                // Optionally show user-friendly error message
            }
        } catch (error) {
            console.error('Error updating task level:', error);
            // Fallback to local storage only
            this.taskData.daily[today][task] = newLevel;

            const completedTasks = this.taskData.daily[today].completed;
            if (newLevel > 0 && !completedTasks.includes(task)) {
                completedTasks.push(task);
            } else if (newLevel === 0 && completedTasks.includes(task)) {
                const index = completedTasks.indexOf(task);
                if (index > -1) {
                    completedTasks.splice(index, 1);
                }
            }

            this.saveData();
            await this.updateDisplay();
            this.checkAchievements();
            this.addCompletionFeedback(task, newLevel);
        }
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
            setTimeout(() => {
                // Remove the temporary animation class after animation
                const completedClass = taskCard.classList.contains('completed');
                if (completedClass) {
                    taskCard.style.animation = 'none';
                    setTimeout(() => { taskCard.style.animation = ''; }, 10);
                }
            }, 600);
        } else {
            taskCard.classList.remove('completed');
        }
    }

    /**
     * Update all display elements
     */
    async updateDisplay() {
        this.updateDateDisplay();
        this.updateProgressCircle();
        this.updateStats();
        this.updateTaskCards();
        await this.updateStreakDisplay();
        this.updateWeeklySummary();
    }

    /**
     * Update date display
     */
    updateDateDisplay() {
        const dateElement = document.getElementById('dateDisplay');
        if (dateElement) {
            const today = this.getPacificDate();
            const options = {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                timeZone: 'America/Los_Angeles'
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

        // Calculate percentage based on completed tasks (out of 3) instead of stars
        const completedTasks = todayData.completed.length;
        const totalTasks = this.tasks.length; // Should be 3
        const percentage = Math.round((completedTasks / totalTasks) * 100);

        const progressCircle = document.getElementById('progressCircle');
        const progressPercentage = document.getElementById('progressPercentage');

        if (progressCircle && progressPercentage) {
            const circumference = 2 * Math.PI * 50; // r = 50
            const strokeDashoffset = circumference - (percentage / 100) * circumference;
            progressCircle.style.strokeDashoffset = strokeDashoffset;
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
            const badge = document.getElementById(`${task}Badge`);

            if (taskCard) {
                // Update star buttons
                const starBtns = taskCard.querySelectorAll('.star-btn');
                starBtns.forEach((btn, index) => {
                    const level = index + 1;
                    if (level <= taskLevel) {
                        btn.classList.add('active');
                    } else {
                        btn.classList.remove('active');
                    }
                });

                // Update task card completion state
                if (taskLevel > 0) {
                    taskCard.classList.add('completed');
                } else {
                    taskCard.classList.remove('completed');
                }
            }

            // Update badge
            if (badge) {
                if (taskLevel === 0) {
                    badge.textContent = 'Not Started';
                    badge.className = 'task-badge';
                } else if (taskLevel < 3) {
                    badge.textContent = 'Started';
                    badge.className = 'task-badge started';
                } else {
                    badge.textContent = 'Completed';
                    badge.className = 'task-badge completed';
                }
            }
        });
    }

    /**
     * Update streak display
     */
    async updateStreakDisplay() {
        const streakCount = document.getElementById('streakCount');
        if (streakCount) {
            // Calculate potential streak including today's progress
            const currentStreak = await this.calculateCurrentStreak();
            streakCount.textContent = currentStreak;
        }
    }

    /**
     * Calculate current streak including today's potential using recursive method
     */
    async calculateCurrentStreak() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        // Check if all tasks have at least 1 star today
        const allTasksCompletedToday = this.tasks.every(task =>
            todayData[task] > 0
        );

        // Calculate historical streak using recursive method
        let currentStreak = await this.calculateTrueStreak();

        // If all tasks are completed today, add 1 to display the potential streak
        if (allTasksCompletedToday) {
            currentStreak += 1;
        }

        return currentStreak;
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
            achievementSection.classList.add('show');

            // Auto hide after 5 seconds
            setTimeout(() => {
                this.hideAchievement();
            }, 5000);
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
    async renderWeeklyGrid() {
        const weeklyGrid = document.getElementById('weeklyGrid');
        if (!weeklyGrid) return;

        weeklyGrid.innerHTML = 'Loading...';

        try {
            // Fetch historical data from backend
            const response = await fetch('/api/history?days=7');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const history = data.history;

            weeklyGrid.innerHTML = '';

            // Get Monday to Sunday of current week in Pacific Time
            const today = this.getPacificDate();
            const currentDay = today.getDay(); // 0 = Sunday, 1 = Monday, etc.
            const mondayOffset = currentDay === 0 ? -6 : 1 - currentDay; // Calculate days to Monday

            const monday = new Date(today);
            monday.setDate(today.getDate() + mondayOffset);

            const weekDays = [];
            for (let i = 0; i < 7; i++) {
                const date = new Date(monday);
                date.setDate(monday.getDate() + i);
                weekDays.push(date);
            }

            weekDays.forEach(date => {
                const dateStr = this.getDateString(date);
                const dayData = history[dateStr];

                const dayCell = document.createElement('div');
                dayCell.className = 'day-cell';

                const dayLabel = document.createElement('div');
                dayLabel.textContent = date.toLocaleDateString('en-US', { weekday: 'short' });
                dayCell.appendChild(dayLabel);

                const dateLabel = document.createElement('div');
                dateLabel.textContent = date.getDate();
                dayCell.appendChild(dateLabel);

                if (dayData) {
                    // Count total stars from the database
                    const totalStars = Object.values(dayData).reduce((sum, val) => {
                        return sum + (typeof val === 'number' ? val : 0);
                    }, 0);

                    // Count completed tasks (tasks with level > 0)
                    const completedTasks = Object.values(dayData).filter(val =>
                        typeof val === 'number' && val > 0
                    ).length;

                    if (completedTasks === 3) {
                        dayCell.classList.add('completed');
                    } else if (totalStars > 0) {
                        dayCell.classList.add('partial');
                    }

                    // Always show stars if there are any, make them more prominent
                    if (totalStars > 0) {
                        const starsLabel = document.createElement('div');
                        // Create multiple rows with max 3 stars per row
                        const starsPerRow = 3;
                        const rows = [];
                        for (let i = 0; i < totalStars; i += starsPerRow) {
                            const starsInRow = Math.min(starsPerRow, totalStars - i);
                            rows.push('⭐'.repeat(starsInRow));
                        }
                        starsLabel.innerHTML = rows.join('<br>');
                        starsLabel.style.fontSize = '0.7rem';
                        starsLabel.style.fontWeight = 'bold';
                        starsLabel.style.color = '#f59e0b';
                        starsLabel.style.marginTop = '2px';
                        starsLabel.style.textShadow = '0 1px 2px rgba(0,0,0,0.1)';
                        starsLabel.style.lineHeight = '1.1';
                        starsLabel.style.textAlign = 'center';
                        dayCell.appendChild(starsLabel);
                    } else {
                        // Show empty state for days with data but no completion
                        const starsLabel = document.createElement('div');
                        starsLabel.textContent = '-';
                        starsLabel.style.fontSize = '0.7rem';
                        starsLabel.style.color = '#9ca3af';
                        starsLabel.style.marginTop = '2px';
                        dayCell.appendChild(starsLabel);
                    }

                    console.log(`Day ${dateStr}: ${totalStars} stars, ${completedTasks} completed tasks`);
                } else {
                    // Show empty state for days without data
                    const emptyLabel = document.createElement('div');
                    emptyLabel.textContent = '-';
                    emptyLabel.style.fontSize = '0.7rem';
                    emptyLabel.style.color = '#9ca3af';
                    emptyLabel.style.marginTop = '2px';
                    dayCell.appendChild(emptyLabel);
                } weeklyGrid.appendChild(dayCell);
            });

        } catch (error) {
            console.error('Error loading weekly data:', error);
            weeklyGrid.innerHTML = 'Error loading weekly data';

            // Fallback to local storage data
            setTimeout(() => {
                this.renderWeeklyGridFromLocal();
            }, 1000);
        }
    }

    /**
     * Fallback method to render weekly grid from local storage
     */
    renderWeeklyGridFromLocal() {
        const weeklyGrid = document.getElementById('weeklyGrid');
        if (!weeklyGrid) return;

        weeklyGrid.innerHTML = '';

        // Get Monday to Sunday of current week in Pacific Time
        const today = this.getPacificDate();
        const currentDay = today.getDay(); // 0 = Sunday, 1 = Monday, etc.
        const mondayOffset = currentDay === 0 ? -6 : 1 - currentDay;

        const monday = new Date(today);
        monday.setDate(today.getDate() + mondayOffset);

        const weekDays = [];
        for (let i = 0; i < 7; i++) {
            const date = new Date(monday);
            date.setDate(monday.getDate() + i);
            weekDays.push(date);
        }

        weekDays.forEach(date => {
            const dateStr = this.getDateString(date);
            const dayData = this.taskData.daily[dateStr];

            const dayCell = document.createElement('div');
            dayCell.className = 'day-cell';

            const dayLabel = document.createElement('div');
            dayLabel.textContent = date.toLocaleDateString('en-US', { weekday: 'short' });
            dayCell.appendChild(dayLabel);

            const dateLabel = document.createElement('div');
            dateLabel.textContent = date.getDate();
            dayCell.appendChild(dateLabel);

            if (dayData) {
                const completedTasks = dayData.completed ? dayData.completed.length : 0;
                const totalStars = Object.values(dayData).reduce((sum, val) => {
                    return sum + (typeof val === 'number' ? val : 0);
                }, 0);

                if (completedTasks === 3) {
                    dayCell.classList.add('completed');
                } else if (totalStars > 0) {
                    dayCell.classList.add('partial');
                }

                // Always show stars if there are any, make them more prominent
                if (totalStars > 0) {
                    const starsLabel = document.createElement('div');
                    // Create multiple rows with max 3 stars per row
                    const starsPerRow = 3;
                    const rows = [];
                    for (let i = 0; i < totalStars; i += starsPerRow) {
                        const starsInRow = Math.min(starsPerRow, totalStars - i);
                        rows.push('⭐'.repeat(starsInRow));
                    }
                    starsLabel.innerHTML = rows.join('<br>');
                    starsLabel.style.fontSize = '0.7rem';
                    starsLabel.style.fontWeight = 'bold';
                    starsLabel.style.color = '#f59e0b';
                    starsLabel.style.marginTop = '2px';
                    starsLabel.style.textShadow = '0 1px 2px rgba(0,0,0,0.1)';
                    starsLabel.style.lineHeight = '1.1';
                    starsLabel.style.textAlign = 'center';
                    dayCell.appendChild(starsLabel);
                } else {
                    // Show empty state for days with data but no completion
                    const starsLabel = document.createElement('div');
                    starsLabel.textContent = '-';
                    starsLabel.style.fontSize = '0.7rem';
                    starsLabel.style.color = '#9ca3af';
                    starsLabel.style.marginTop = '2px';
                    dayCell.appendChild(starsLabel);
                }

                console.log(`Day ${dateStr} (local): ${totalStars} stars, ${completedTasks} completed tasks`);
            } else {
                // Show empty state for days without data
                const emptyLabel = document.createElement('div');
                emptyLabel.textContent = '-';
                emptyLabel.style.fontSize = '0.7rem';
                emptyLabel.style.color = '#9ca3af';
                emptyLabel.style.marginTop = '2px';
                dayCell.appendChild(emptyLabel);
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
        console.error('Error starting WellnessTracker:', error);
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