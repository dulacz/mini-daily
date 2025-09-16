'use strict';

/**
 * Multi-User Daily Wellness Tracker Application
 * Manages task completion, streaks, and progress tracking for multiple users
 */
class WellnessTracker {
    constructor() {
        this.currentUser = 'alice'; // Default user
        this.userConfigs = {}; // Will be loaded from backend
        this.users = []; // Will be loaded from backend
        this.tasks = []; // Will be loaded for current user
        this.taskLevels = {}; // Will be loaded for current user
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

            // Generate user tabs
            this.generateUserTabs();

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
                this.userConfigs = config.user_configs || {};
                this.users = config.users || ['alice'];
                this.currentUser = config.default_user || 'alice';

                // Set current user's tasks and levels
                await this.setCurrentUser(this.currentUser);

                console.log('Loaded multi-user config:', config);
            } else {
                throw new Error('Failed to load config');
            }
        } catch (error) {
            console.error('Error loading config, using defaults:', error);
            // Use fallback values if config loading fails
            this.userConfigs = {
                alice: {
                    name: 'Alice',
                    tasks: {
                        reading: { title: 'Reading', icon: '📚' },
                        exercise: { title: 'Exercise', icon: '💪' },
                        caring: { title: 'Self-Care', icon: '❤️' }
                    }
                }
            };
            this.users = ['alice'];
            this.currentUser = 'alice';
            await this.setCurrentUser(this.currentUser);
        }
    }

    /**
     * Set current user and update related data
     */
    async setCurrentUser(user) {
        this.currentUser = user;
        const userConfig = this.userConfigs[user] || this.userConfigs[Object.keys(this.userConfigs)[0]];
        this.taskLevels = userConfig.tasks || {};
        this.tasks = Object.keys(this.taskLevels);

        // Update page title
        const appTitle = document.getElementById('appTitle');
        if (appTitle) {
            appTitle.textContent = `${userConfig.name || user}'s Check-in`;
        }

        // Update CSS custom property for user color
        if (userConfig.color) {
            document.documentElement.style.setProperty('--user-color', userConfig.color);
        }

        // Generate task cards for current user
        this.generateTaskCards();
    }

    /**
     * Generate user tabs dynamically from configuration
     */
    generateUserTabs() {
        const userTabs = document.getElementById('userTabs');
        if (!userTabs) return;

        userTabs.innerHTML = ''; // Clear existing content

        this.users.forEach(userId => {
            const userConfig = this.userConfigs[userId];
            const tabButton = document.createElement('button');
            tabButton.className = 'user-tab';
            tabButton.setAttribute('data-user', userId);

            if (userId === this.currentUser) {
                tabButton.classList.add('active');
            }

            // Get first task icon as user icon (or use default)
            const firstTaskIcon = Object.values(userConfig.tasks || {})[0]?.icon || '👤';

            tabButton.innerHTML = `
                <span class="user-tab-icon">${firstTaskIcon}</span>
                <span class="user-tab-name">${userConfig.name || userId}</span>
            `;

            tabButton.addEventListener('click', () => this.switchUser(userId));
            userTabs.appendChild(tabButton);
        });
    }

    /**
     * Switch to a different user
     */
    async switchUser(userId) {
        if (userId === this.currentUser) return;

        // Update active tab
        document.querySelectorAll('.user-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.user === userId);
        });

        // Switch user and reload data
        await this.setCurrentUser(userId);
        this.taskData = this.loadData();
        await this.checkNewDay();
        this.updateDisplay();
        await this.syncWithBackend();
    }
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
     * Sync local data with backend for current user
     */
    async syncWithBackend() {
        try {
            const response = await fetch(`/api/user/${this.currentUser}/status/today`);
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
     * Load data from localStorage for current user
     * @returns {Object} Task data object
     */
    loadData() {
        try {
            const storageKey = `wellnessData_${this.currentUser}`;
            if (typeof Storage !== "undefined" && localStorage.getItem(storageKey)) {
                const data = JSON.parse(localStorage.getItem(storageKey));
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
     * Get default data structure for current user
     * @returns {Object} Default task data
     */
    getDefaultData() {
        const today = this.getDateString();
        const defaultData = {
            currentDate: today,
            daily: {
                [today]: {
                    completed: []
                }
            },
            streaks: {
                overall: 0
            },
            achievements: []
        };

        // Initialize tasks for current user
        this.tasks.forEach(task => {
            defaultData.daily[today][task] = 0;
        });

        return defaultData;
    }

    /**
     * Save data to localStorage for current user
     */
    saveData() {
        try {
            if (typeof Storage !== "undefined") {
                const storageKey = `wellnessData_${this.currentUser}`;
                localStorage.setItem(storageKey, JSON.stringify(this.taskData));
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
            // Fetch historical data from backend for current user
            const response = await fetch(`/api/user/${this.currentUser}/history?days=365`);
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

        // Monthly summary toggle
        const monthlySummaryToggle = document.getElementById('monthlySummaryToggle');
        if (monthlySummaryToggle) {
            monthlySummaryToggle.addEventListener('click', () => this.toggleMonthlySummary());
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
            // Call backend API to update database for current user
            const response = await fetch(`/api/user/${this.currentUser}/task/level`, {
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
        await this.updateStarDisplay();
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
     * Update star counter display (365 days)
     */
    async updateStarDisplay() {
        const starCount = document.getElementById('starCount');
        if (starCount) {
            const totalStars = await this.calculateTotalStars365();
            starCount.textContent = totalStars;
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
     * Calculate total stars within 365 days using backend API
     */
    async calculateTotalStars365() {
        try {
            const response = await fetch(`/api/user/${this.currentUser}/history?days=365`);
            if (!response.ok) {
                throw new Error('Failed to fetch history data');
            }

            const data = await response.json();
            const history = data.history;
            let totalStars = 0;

            // Calculate total stars from backend data
            // Iterate over all dates in the history object
            for (const dateStr in history) {
                const dayData = history[dateStr];
                // dayData is an object like {caring: 3, exercise: 1, reading: 3}
                // Sum all task levels for this date
                for (const task in dayData) {
                    if (typeof dayData[task] === 'number') {
                        totalStars += dayData[task];
                    }
                }
            }

            // Add today's stars from local data
            const today = this.getDateString();
            const todayData = this.taskData.daily[today];
            const todayStars = Object.values(todayData).reduce((sum, val) => {
                return sum + (typeof val === 'number' ? val : 0);
            }, 0);
            totalStars += todayStars;

            return totalStars;
        } catch (error) {
            console.error('Error calculating 365-day star total:', error);
            // Fallback to local calculation if backend fails
            return this.calculateTotalStarsLocal365();
        }
    }

    /**
     * Fallback method to calculate total stars from local storage (limited data)
     */
    calculateTotalStarsLocal365() {
        let totalStars = 0;
        const today = new Date();

        // Calculate for the last 365 days using available local data
        for (let i = 0; i < 365; i++) {
            const checkDate = new Date(today);
            checkDate.setDate(checkDate.getDate() - i);
            const dateStr = this.getDateString(checkDate);

            const dayData = this.taskData.daily[dateStr];
            if (dayData) {
                Object.values(dayData).forEach(val => {
                    if (typeof val === 'number') {
                        totalStars += val;
                    }
                });
            }
        }

        return totalStars;
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
            // Fetch historical data from backend for current user
            const response = await fetch(`/api/user/${this.currentUser}/history?days=7`);
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

    /**
     * Toggle monthly summary display
     */
    toggleMonthlySummary() {
        const summaryContent = document.getElementById('monthlySummaryContent');
        const summaryToggle = document.getElementById('monthlySummaryToggle');

        if (summaryContent && summaryToggle) {
            const isVisible = summaryContent.style.display !== 'none';

            if (isVisible) {
                summaryContent.style.display = 'none';
                summaryToggle.classList.remove('active');
            } else {
                summaryContent.style.display = 'block';
                summaryToggle.classList.add('active');
                this.renderMonthlyGrid();
            }
        }
    }

    /**
     * Render monthly progress grid
     */
    async renderMonthlyGrid() {
        const monthlyGrid = document.getElementById('monthlyGrid');
        const monthlyTitle = document.getElementById('monthlyTitle');
        if (!monthlyGrid) return;

        monthlyGrid.innerHTML = 'Loading...';

        try {
            // Get current month info
            const today = this.getPacificDate();
            const currentMonth = today.getMonth();
            const currentYear = today.getFullYear();
            const todayDateStr = this.getDateString();

            // Update title
            const monthName = today.toLocaleDateString('en-US', {
                month: 'long',
                year: 'numeric',
                timeZone: 'America/Los_Angeles'
            });
            if (monthlyTitle) {
                monthlyTitle.textContent = `${monthName} Progress`;
            }

            // Get first day of month and determine starting day of week
            const firstDay = new Date(currentYear, currentMonth, 1);
            const lastDay = new Date(currentYear, currentMonth + 1, 0);
            const daysInMonth = lastDay.getDate();
            const startingDayOfWeek = firstDay.getDay(); // 0 = Sunday, 1 = Monday, etc.

            // Calculate how many days to fetch (including some before/after for context)
            const totalDays = Math.max(35, daysInMonth + startingDayOfWeek);

            // Fetch historical data
            const response = await fetch(`/api/user/${this.currentUser}/history?days=${totalDays}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const history = data.history;

            monthlyGrid.innerHTML = '';

            // Create a container for the entire monthly view
            const monthlyContainer = document.createElement('div');

            // Add day headers (Sun, Mon, Tue, etc.)
            const dayHeaders = document.createElement('div');
            dayHeaders.className = 'month-header';
            const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            dayNames.forEach(dayName => {
                const dayHeader = document.createElement('div');
                dayHeader.className = 'day-header';
                dayHeader.textContent = dayName;
                dayHeaders.appendChild(dayHeader);
            });
            monthlyContainer.appendChild(dayHeaders);

            // Create the monthly grid container
            const gridContainer = document.createElement('div');
            gridContainer.style.display = 'grid';
            gridContainer.style.gridTemplateColumns = 'repeat(7, 1fr)';
            gridContainer.style.gap = '0.5rem';

            const totalCells = Math.ceil((daysInMonth + startingDayOfWeek) / 7) * 7;

            for (let i = 0; i < totalCells; i++) {
                const dayCell = document.createElement('div');
                dayCell.className = 'day-cell';

                const dayNumber = i - startingDayOfWeek + 1;

                if (dayNumber <= 0 || dayNumber > daysInMonth) {
                    // Outside current month - empty cell
                    dayCell.classList.add('outside-month');
                } else {
                    // Valid day in current month
                    const date = new Date(currentYear, currentMonth, dayNumber);
                    const dateStr = this.getDateString(date);

                    // Add day number
                    const dayLabel = document.createElement('div');
                    dayLabel.textContent = dayNumber;
                    dayLabel.style.fontWeight = 'bold';
                    dayCell.appendChild(dayLabel);

                    // Check if this is today
                    if (dateStr === todayDateStr) {
                        dayCell.classList.add('today');
                    }

                    const dayData = history[dateStr];

                    if (dayData) {
                        // Count total stars and completed tasks
                        const totalStars = Object.values(dayData).reduce((sum, val) => {
                            return sum + (typeof val === 'number' ? val : 0);
                        }, 0);

                        const completedTasks = Object.values(dayData).filter(val =>
                            typeof val === 'number' && val > 0
                        ).length;

                        if (completedTasks === 3) {
                            dayCell.classList.add('completed');
                        } else if (totalStars > 0) {
                            dayCell.classList.add('partial');
                        }

                        // Show stars if there are any
                        if (totalStars > 0) {
                            const starsLabel = document.createElement('div');
                            const starsPerRow = 3;
                            const rows = [];
                            for (let j = 0; j < totalStars; j += starsPerRow) {
                                const starsInRow = Math.min(starsPerRow, totalStars - j);
                                rows.push('⭐'.repeat(starsInRow));
                            }
                            starsLabel.innerHTML = rows.join('<br>');
                            starsLabel.style.fontSize = '0.6rem';
                            starsLabel.style.fontWeight = 'bold';
                            starsLabel.style.color = '#f59e0b';
                            starsLabel.style.marginTop = '2px';
                            starsLabel.style.textShadow = '0 1px 2px rgba(0,0,0,0.1)';
                            starsLabel.style.lineHeight = '1';
                            starsLabel.style.textAlign = 'center';
                            dayCell.appendChild(starsLabel);
                        } else {
                            // Show empty state for days with data but no completion
                            const starsLabel = document.createElement('div');
                            starsLabel.textContent = '-';
                            starsLabel.style.fontSize = '0.6rem';
                            starsLabel.style.color = '#9ca3af';
                            starsLabel.style.marginTop = '2px';
                            dayCell.appendChild(starsLabel);
                        }
                    } else {
                        // Show empty state for days without data
                        const emptyLabel = document.createElement('div');
                        emptyLabel.textContent = '-';
                        emptyLabel.style.fontSize = '0.6rem';
                        emptyLabel.style.color = '#9ca3af';
                        emptyLabel.style.marginTop = '2px';
                        dayCell.appendChild(emptyLabel);
                    }
                }

                gridContainer.appendChild(dayCell);
            }

            monthlyContainer.appendChild(gridContainer);
            monthlyGrid.appendChild(monthlyContainer);

        } catch (error) {
            console.error('Error loading monthly data:', error);
            monthlyGrid.innerHTML = 'Error loading monthly data';
        }
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