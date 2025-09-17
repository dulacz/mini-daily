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
            { id: 'month_streak', title: 'Monthly Master!', message: '30 days of consistency - amazing!', triggered: false }
        ];
        this.init();
    }

    /**
     * Initialize the application
     */
    async init() {
        try {
            // Initialize theme from localStorage
            this.initializeTheme();

            // Load configuration from backend first
            await this.loadConfig();

            // Set initial user background
            this.updateUserBackground();

            // Generate user tabs
            this.generateUserTabs();

            await this.checkNewDay();
            this.setupEventListeners();
            this.updateDisplay();

            // Create animated background particles
            this.createParticles();

            // Start auto theme checker
            this.startAutoThemeChecker();

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

        // Update background gradient for new user
        this.updateUserBackground(userId);

        // Collapse monthly summary when switching users
        const summaryContent = document.getElementById('monthlySummaryContent');
        const summaryToggle = document.getElementById('monthlySummaryToggle');
        if (summaryContent && summaryToggle) {
            summaryContent.style.display = 'none';
            summaryToggle.classList.remove('active');
        }

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

            // Check if this task has activities (hierarchical structure)
            const activities = taskConfig?.activities;

            if (activities && Object.keys(activities).length > 0) {
                // New hierarchical structure - show activity selection first
                taskCard.innerHTML = this.generateHierarchicalTaskCard(taskId, title, icon, description, activities);
            } else {
                // Legacy structure - direct level selection
                const levels = taskConfig?.levels || { 1: "Level 1", 2: "Level 2", 3: "Level 3" };
                taskCard.innerHTML = this.generateLegacyTaskCard(taskId, title, icon, description, levels);
            }

            tasksContainer.appendChild(taskCard);
        });

        // Re-setup event listeners for the new buttons
        this.setupTaskEventListeners();

        // Load existing notes for tasks
        this.loadTaskNotes();
    }

    /**
     * Generate task card for new hierarchical structure (task -> activity -> levels)
     */
    generateHierarchicalTaskCard(taskId, title, icon, description, activities) {
        return `
            <div class="task-header">
                <div class="task-icon">${icon}</div>
                <h3 class="task-title">${title}</h3>
                <div class="task-badge not-started" id="${taskId}Badge">Not Started</div>
            </div>
            <div class="task-description">
                <span class="task-desc-text">${description}</span>
            </div>
            
            <!-- Activity Selection Phase -->
            <div class="activity-selection" id="${taskId}ActivitySelection">
                <div class="activity-buttons">
                    ${Object.entries(activities).map(([activityId, activityConfig]) => `
                        <button class="activity-btn" data-task="${taskId}" data-activity="${activityId}">
                            <div class="activity-content">
                                <span class="activity-label">${activityConfig.label || this.capitalizeFirst(activityId)}</span>
                                <div class="activity-progress" id="${taskId}_${activityId}_progress">
                                    <span class="progress-dots">
                                        <span class="progress-dot"></span>
                                        <span class="progress-dot"></span>
                                        <span class="progress-dot"></span>
                                    </span>
                                </div>
                            </div>
                        </button>
                    `).join('')}
                </div>
            </div>
            
            <!-- Level Selection Phase (initially hidden) -->
            <div class="level-selection" id="${taskId}LevelSelection" style="display: none;">
                <h4 id="${taskId}LevelTitle">Choose Level:</h4>
                <div class="star-rating" data-task="${taskId}" id="${taskId}StarRating">
                    <!-- Levels will be populated when activity is selected -->
                </div>
                <button class="back-to-activities-btn" data-task="${taskId}">← Back to Activities</button>
            </div>
            
            <!-- Note Section -->
            <div class="task-note-section" data-task="${taskId}" id="${taskId}NoteSection" style="display: none;">
                <div class="note-display" id="${taskId}NoteDisplay" style="display: none;">
                    <div class="note-content" id="${taskId}NoteContent"></div>
                    <button class="note-edit-btn" data-task="${taskId}">Edit Note</button>
                </div>
                <div class="note-input-section" id="${taskId}NoteInput">
                    <textarea class="note-input" id="${taskId}NoteTextarea" placeholder="Add a note about your progress..." rows="2"></textarea>
                    <div class="note-buttons">
                        <button class="note-save-btn" data-task="${taskId}">Save Note</button>
                        <button class="note-cancel-btn" data-task="${taskId}" style="display: none;">Cancel</button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Generate task card for legacy structure (direct level selection)
     */
    generateLegacyTaskCard(taskId, title, icon, description, levels) {
        return `
            <div class="task-header">
                <div class="task-icon">${icon}</div>
                <h3 class="task-title">${title}</h3>
                <div class="task-badge not-started" id="${taskId}Badge">Not Started</div>
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
            <div class="task-note-section" data-task="${taskId}">
                <div class="note-display" id="${taskId}NoteDisplay" style="display: none;">
                    <div class="note-content" id="${taskId}NoteContent"></div>
                    <button class="note-edit-btn" data-task="${taskId}">Edit Note</button>
                </div>
                <div class="note-input-section" id="${taskId}NoteInput">
                    <textarea class="note-input" id="${taskId}NoteTextarea" placeholder="Add a note about your progress..." rows="2"></textarea>
                    <div class="note-buttons">
                        <button class="note-save-btn" data-task="${taskId}">Save Note</button>
                        <button class="note-cancel-btn" data-task="${taskId}" style="display: none;">Cancel</button>
                    </div>
                </div>
            </div>
        `;
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
                    // Handle new data format where status contains objects with level and note
                    const dailyData = { completed: [] };

                    Object.keys(data.status).forEach(task => {
                        const taskData = data.status[task];
                        if (typeof taskData === 'object' && taskData.level !== undefined) {
                            // New format with level and note
                            dailyData[task] = taskData.level;
                            if (taskData.level > 0) {
                                dailyData.completed.push(task);
                            }
                        } else {
                            // Legacy format - just level
                            dailyData[task] = taskData;
                            if (taskData > 0) {
                                dailyData.completed.push(task);
                            }
                        }
                    });

                    this.taskData.daily[today] = {
                        ...this.taskData.daily[today],
                        ...dailyData
                    };

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
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Setup task-specific listeners (will be called after task cards are generated)
        this.setupTaskEventListeners();

        // Monthly summary toggle
        const monthlySummaryToggle = document.getElementById('monthlySummaryToggle');
        if (monthlySummaryToggle) {
            monthlySummaryToggle.addEventListener('click', () => this.toggleMonthlySummary());
        }

        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());

            // Double-click to re-enable auto theme
            themeToggle.addEventListener('dblclick', () => {
                this.enableAutoTheme();
                // Show a brief confirmation
                const originalText = themeToggle.textContent;
                themeToggle.textContent = '🔄';
                setTimeout(() => {
                    const body = document.body;
                    themeToggle.textContent = body.classList.contains('dark-theme') ? '☀️' : '🌙';
                }, 1000);
            });
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
        // Star button clicks (legacy structure)
        document.querySelectorAll('.star-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleStarClick(e));
        });

        // Activity button clicks (new hierarchical structure)
        document.querySelectorAll('.activity-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleActivitySelect(e));
        });

        // Back to activities button clicks (new hierarchical structure)
        document.querySelectorAll('.back-to-activities-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleBackToActivities(e));
        });

        // Note save button clicks
        document.querySelectorAll('.note-save-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleNoteSave(e));
        });

        // Note edit button clicks
        document.querySelectorAll('.note-edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleNoteEdit(e));
        });

        // Note cancel button clicks
        document.querySelectorAll('.note-cancel-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleNoteCancel(e));
        });
    }

    /**
     * Handle activity selection (new hierarchical structure)
     */
    async handleActivitySelect(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;
        const activity = btn.dataset.activity;

        try {
            // Get levels for this activity
            const levelsResponse = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activity}/levels`);
            if (!levelsResponse.ok) throw new Error('Failed to load activity levels');

            const levelsData = await levelsResponse.json();
            const levels = levelsData.levels;

            // Get current status for this activity
            const statusResponse = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activity}/status`);
            let currentLevel = 0;
            let currentNote = '';

            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                currentLevel = statusData.level || 0;
                currentNote = statusData.note || '';
            }

            // Hide activity selection, show level selection
            const activitySelection = document.getElementById(`${task}ActivitySelection`);
            const levelSelection = document.getElementById(`${task}LevelSelection`);
            const levelTitle = document.getElementById(`${task}LevelTitle`);
            const starRating = document.getElementById(`${task}StarRating`);

            if (activitySelection) activitySelection.style.display = 'none';
            if (levelSelection) levelSelection.style.display = 'block';

            // Update level title
            if (levelTitle) {
                const activityConfig = this.taskLevels[task]?.activities?.[activity];
                const activityLabel = activityConfig?.label || this.capitalizeFirst(activity);
                levelTitle.textContent = `${activityLabel} - Choose Level:`;
            }

            // Generate level buttons
            if (starRating) {
                starRating.innerHTML = Object.entries(levels).map(([level, desc]) => {
                    const levelNum = parseInt(level);
                    const isActive = levelNum <= currentLevel ? 'active' : '';
                    return `
                        <button class="star-btn ${isActive}" data-task="${task}" data-activity="${activity}" data-level="${level}" title="${desc}">
                            <span class="star-icon">⭐</span>
                            <span class="star-label">${desc}</span>
                        </button>
                    `;
                }).join('');

                // Add event listeners to new star buttons
                starRating.querySelectorAll('.star-btn').forEach(starBtn => {
                    starBtn.addEventListener('click', (e) => this.handleActivityStarClick(e));
                });
            }

            // Update task badge to show simplified status
            const badge = document.getElementById(`${task}Badge`);
            if (badge) {
                if (currentLevel > 0) {
                    badge.textContent = 'Completed';
                    badge.className = 'task-badge completed';
                } else {
                    badge.textContent = 'Not Started';
                    badge.className = 'task-badge not-started';
                }
            }

            // Show note section if there's a current note or level
            const noteSection = document.getElementById(`${task}NoteSection`);
            if (noteSection && (currentLevel > 0 || currentNote)) {
                noteSection.style.display = 'block';

                // Update note content if exists
                if (currentNote) {
                    const noteContent = document.getElementById(`${task}NoteContent`);
                    const noteDisplay = document.getElementById(`${task}NoteDisplay`);
                    const noteInput = document.getElementById(`${task}NoteInput`);

                    if (noteContent && noteDisplay && noteInput) {
                        noteContent.textContent = currentNote;
                        noteDisplay.style.display = 'block';
                        noteInput.style.display = 'none';
                    }
                }
            }

        } catch (error) {
            console.error('Error loading activity levels:', error);
        }
    }

    /**
     * Handle back to activities button click
     */
    async handleBackToActivities(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;

        // Show activity selection, hide level selection
        const activitySelection = document.getElementById(`${task}ActivitySelection`);
        const levelSelection = document.getElementById(`${task}LevelSelection`);
        const noteSection = document.getElementById(`${task}NoteSection`);

        if (activitySelection) activitySelection.style.display = 'block';
        if (levelSelection) levelSelection.style.display = 'none';
        if (noteSection) noteSection.style.display = 'none';

        // Update badge with current actual status instead of resetting to "Not Started"
        const badge = document.getElementById(`${task}Badge`);
        if (badge) {
            await this.updateTaskBadgeStatus(task, badge);
        }

        // Update activity progress indicators to reflect current state
        await this.updateActivityProgress();

        // Refresh top-level statistics (completion %, tasks done, stars today)
        await this.updateProgressCircle();
        await this.updateStats();
        await this.updateStarDisplay();
    }

    /**
     * Handle star clicks for hierarchical structure (task-activity-level)
     */
    async handleActivityStarClick(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;
        const activity = btn.dataset.activity;
        const level = parseInt(btn.dataset.level);

        // Get current level from UI to implement toggle behavior
        const starRating = btn.closest('.star-rating');
        const allStars = starRating.querySelectorAll('.star-btn');

        // Count currently active stars to determine current level
        let currentLevel = 0;
        allStars.forEach(star => {
            if (star.classList.contains('active')) {
                currentLevel = Math.max(currentLevel, parseInt(star.dataset.level));
            }
        });

        // Toggle behavior: if clicking the same level, set to 0, otherwise set to clicked level
        const newLevel = currentLevel === level ? 0 : level;

        await this.setTaskActivityLevel(task, activity, newLevel);
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
     * Set task-activity completion level (new hierarchical structure)
     * @param {string} task - Task name
     * @param {string} activity - Activity name
     * @param {number} level - Completion level (1-3)
     */
    async setTaskActivityLevel(task, activity, level) {
        try {
            // Call backend API to update database for current user
            const response = await fetch(`/api/user/${this.currentUser}/task/activity/level`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task: task,
                    activity: activity,
                    level: level
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            if (result.success) {
                // Update UI to show completion
                this.updateTaskActivityUI(task, activity, level);

                // Show note section
                const noteSection = document.getElementById(`${task}NoteSection`);
                if (noteSection) noteSection.style.display = 'block';

                // Update task badge with actual status across all activities
                const badge = document.getElementById(`${task}Badge`);
                if (badge) {
                    await this.updateTaskBadgeStatus(task, badge);
                }

                // Update activity progress indicators to reflect the change
                await this.updateActivityProgress();

                // Refresh top-level statistics (completion %, tasks done, stars today)
                await this.updateProgressCircle();
                await this.updateStats();
                await this.updateStarDisplay();

                // Add visual feedback
                this.addCompletionFeedback(task, level);
                this.checkAchievements();

            } else {
                console.error('Failed to update task activity level:', result.error);
            }
        } catch (error) {
            console.error('Error updating task activity level:', error);
        }
    }

    /**
     * Update UI for task-activity completion
     */
    updateTaskActivityUI(task, activity, level) {
        // Highlight selected level
        const starButtons = document.querySelectorAll(`[data-task="${task}"][data-activity="${activity}"].star-btn`);
        starButtons.forEach((btn, index) => {
            const btnLevel = parseInt(btn.dataset.level);
            if (btnLevel <= level) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
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
     * Handle note save button clicks
     * @param {Event} event - Click event
     */
    async handleNoteSave(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;
        const textarea = document.getElementById(`${task}NoteTextarea`);
        const note = textarea.value.trim();

        try {
            // Call backend API to save note
            const response = await fetch(`/api/user/${this.currentUser}/task/note`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task: task,
                    note: note
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    // Update note display
                    this.updateNoteDisplay(task, note);
                    // Show success feedback
                    btn.textContent = 'Saved!';
                    btn.style.background = 'var(--success-color)';
                    setTimeout(() => {
                        btn.textContent = 'Save Note';
                        btn.style.background = '';
                    }, 2000);
                }
            }
        } catch (error) {
            console.error('Error saving note:', error);
            // Show error feedback
            btn.textContent = 'Error!';
            btn.style.background = 'var(--error-color, #ef4444)';
            setTimeout(() => {
                btn.textContent = 'Save Note';
                btn.style.background = '';
            }, 2000);
        }
    }

    /**
     * Handle note edit button clicks
     * @param {Event} event - Click event
     */
    handleNoteEdit(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;
        const noteDisplay = document.getElementById(`${task}NoteDisplay`);
        const noteInput = document.getElementById(`${task}NoteInput`);
        const textarea = document.getElementById(`${task}NoteTextarea`);
        const noteContent = document.getElementById(`${task}NoteContent`);
        const cancelBtn = noteInput.querySelector('.note-cancel-btn');

        // Switch to edit mode
        noteDisplay.style.display = 'none';
        noteInput.style.display = 'block';
        cancelBtn.style.display = 'inline-block';

        // Populate textarea with current note content
        textarea.value = noteContent.textContent;
        textarea.focus();
    }

    /**
     * Handle note cancel button clicks
     * @param {Event} event - Click event
     */
    handleNoteCancel(event) {
        const btn = event.currentTarget;
        const task = btn.dataset.task;
        const noteDisplay = document.getElementById(`${task}NoteDisplay`);
        const noteInput = document.getElementById(`${task}NoteInput`);
        const textarea = document.getElementById(`${task}NoteTextarea`);

        // Reset textarea and switch back to display mode
        textarea.value = '';
        btn.style.display = 'none';

        // Only show display if there's a note to show
        if (noteDisplay.querySelector('.note-content').textContent.trim()) {
            noteDisplay.style.display = 'block';
            noteInput.style.display = 'none';
        }
    }

    /**
     * Update note display for a task
     * @param {string} task - Task name
     * @param {string} note - Note text
     */
    updateNoteDisplay(task, note) {
        const noteDisplay = document.getElementById(`${task}NoteDisplay`);
        const noteInput = document.getElementById(`${task}NoteInput`);
        const noteContent = document.getElementById(`${task}NoteContent`);
        const textarea = document.getElementById(`${task}NoteTextarea`);
        const cancelBtn = noteInput.querySelector('.note-cancel-btn');

        noteContent.textContent = note;

        if (note.trim()) {
            // Show note display, hide input
            noteDisplay.style.display = 'block';
            noteInput.style.display = 'none';
        } else {
            // Show input, hide display
            noteDisplay.style.display = 'none';
            noteInput.style.display = 'block';
        }

        // Reset input state
        textarea.value = '';
        cancelBtn.style.display = 'none';
    }

    /**
     * Load existing notes for current user
     */
    async loadTaskNotes() {
        for (const task of this.tasks) {
            try {
                const response = await fetch(`/api/user/${this.currentUser}/task/${task}/note`);
                if (response.ok) {
                    const result = await response.json();
                    this.updateNoteDisplay(task, result.note || '');
                }
            } catch (error) {
                console.error(`Error loading note for task ${task}:`, error);
            }
        }
    }

    /**
     * Update all display elements
     */
    async updateDisplay() {
        this.updateDateDisplay();
        await this.updateProgressCircle();
        await this.updateStats();
        this.updateTaskCards();
        await this.updateStreakDisplay();
        await this.updateStarDisplay();
        await this.updateActivityProgress();
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
    async updateProgressCircle() {
        // Calculate completion based on real-time task status
        let completedTasksCount = 0;

        for (const task of this.tasks) {
            const taskConfig = this.taskLevels[task];
            if (taskConfig && taskConfig.activities) {
                let hasAnyStars = false;

                // Check each activity to see if any has stars
                for (const activityId of Object.keys(taskConfig.activities)) {
                    try {
                        const response = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activityId}/status`);
                        if (response.ok) {
                            const activityData = await response.json();
                            if (activityData.level && activityData.level > 0) {
                                hasAnyStars = true;
                                break;
                            }
                        }
                    } catch (error) {
                        console.error(`Error checking activity status for ${task}/${activityId}:`, error);
                    }
                }

                if (hasAnyStars) {
                    completedTasksCount++;
                }
            }
        }

        const totalTasks = this.tasks.length; // Should be 3
        const percentage = Math.round((completedTasksCount / totalTasks) * 100);

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
    async updateStats() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        // Calculate both total stars and completion using real-time data for consistency
        let totalStars = 0;
        let completedTasksCount = 0;

        for (const task of this.tasks) {
            const taskConfig = this.taskLevels[task];
            if (taskConfig && taskConfig.activities) {
                let hasAnyStars = false;
                let taskStars = 0;

                // Check each activity to see if any has stars and sum up the stars
                for (const activityId of Object.keys(taskConfig.activities)) {
                    try {
                        const response = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activityId}/status`);
                        if (response.ok) {
                            const activityData = await response.json();
                            if (activityData.level && activityData.level > 0) {
                                hasAnyStars = true;
                                taskStars += activityData.level;
                            }
                        }
                    } catch (error) {
                        console.error(`Error checking activity status for ${task}/${activityId}:`, error);
                    }
                }

                totalStars += taskStars;

                if (hasAnyStars) {
                    completedTasksCount++;
                }
            }
        }

        const totalStarsElement = document.getElementById('totalStars');
        const completedTasksElement = document.getElementById('completedTasks');

        if (totalStarsElement) totalStarsElement.textContent = totalStars;
        if (completedTasksElement) completedTasksElement.textContent = completedTasksCount;
    }

    /**
     * Update task cards display
     */
    updateTaskCards() {
        const today = this.getDateString();
        const todayData = this.taskData.daily[today];

        this.tasks.forEach(async (task) => {
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

            // Update badge - check actual activity levels instead of cached task level
            if (badge) {
                await this.updateTaskBadgeStatus(task, badge);
            }
        });

        // Load notes for current tasks
        this.loadTaskNotes();
    }

    /**
     * Update badge status by checking actual activity levels
     */
    async updateTaskBadgeStatus(task, badge) {
        const taskConfig = this.taskLevels[task];
        if (!taskConfig || !taskConfig.activities) {
            badge.textContent = 'Not Started';
            badge.className = 'task-badge not-started';
            return;
        }

        let hasAnyStars = false;

        // Check each activity to see if any has stars
        for (const activityId of Object.keys(taskConfig.activities)) {
            try {
                const response = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activityId}/status`);
                if (response.ok) {
                    const activityData = await response.json();
                    if (activityData.level && activityData.level > 0) {
                        hasAnyStars = true;
                        break;
                    }
                }
            } catch (error) {
                console.error(`Error checking activity status for ${task}/${activityId}:`, error);
            }
        }

        // Update badge based on actual activity levels
        if (hasAnyStars) {
            badge.textContent = 'Completed';
            badge.className = 'task-badge completed';
        } else {
            badge.textContent = 'Not Started';
            badge.className = 'task-badge not-started';
        }
    }

    /**
     * Update activity progress indicators
     */
    async updateActivityProgress() {
        // Update each activity progress indicator
        for (const taskId of this.tasks) {
            const taskConfig = this.taskLevels[taskId];
            if (!taskConfig || !taskConfig.activities) continue;

            for (const activityId of Object.keys(taskConfig.activities)) {
                const progressElement = document.getElementById(`${taskId}_${activityId}_progress`);
                if (!progressElement) continue;

                try {
                    // Get activity status from backend
                    const response = await fetch(`/api/user/${this.currentUser}/task/${taskId}/activity/${activityId}/status`);
                    if (!response.ok) {
                        console.warn(`Failed to fetch status for ${taskId}/${activityId}`);
                        continue;
                    }

                    const activityData = await response.json();
                    const currentLevel = activityData.level || 0;
                    const maxLevel = 3;

                    // Update progress dots
                    const dots = progressElement.querySelectorAll('.progress-dot');
                    dots.forEach((dot, index) => {
                        if (index < currentLevel) {
                            dot.classList.add('active');
                        } else {
                            dot.classList.remove('active');
                        }
                    });

                } catch (error) {
                    console.error(`Error updating progress for ${taskId}/${activityId}:`, error);
                }
            }
        }
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
            // The backend already provides MAX level per task per day
            for (const dateStr in history) {
                const dayData = history[dateStr];
                // dayData is an object like {knowledge: 3, fitness: 1, creativity: 3}
                // Sum all task levels for this date (already MAX levels from backend)
                for (const task in dayData) {
                    if (typeof dayData[task] === 'number') {
                        totalStars += dayData[task];
                    }
                }
            }

            // Add today's stars from local data (only count task levels)
            const today = this.getDateString();
            const todayData = this.taskData.daily[today];
            let todayStars = 0;
            this.tasks.forEach(task => {
                const taskLevel = todayData[task] || 0;
                todayStars += (typeof taskLevel === 'number' ? taskLevel : 0);
            });
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
                // Only count task levels, not other properties like 'completed' array
                this.tasks.forEach(task => {
                    const taskLevel = dayData[task] || 0;
                    if (typeof taskLevel === 'number') {
                        totalStars += taskLevel;
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

        // First star achievement - calculate total stars properly
        let totalStars = 0;
        this.tasks.forEach(task => {
            const taskLevel = todayData[task] || 0;
            totalStars += (typeof taskLevel === 'number' ? taskLevel : 0);
        });

        if (totalStars > 0 && !this.taskData.achievements.includes('first_star')) {
            this.triggerAchievement('first_star');
        }

        // All tasks completed achievement
        if (todayData.completed.length === 3 && !this.taskData.achievements.includes('all_tasks')) {
            this.triggerAchievement('all_tasks');
        }

        // Streak achievements
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
            gridContainer.style.gap = '0.35rem';

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
                    dayLabel.className = 'day-number';
                    dayLabel.textContent = dayNumber;
                    dayCell.appendChild(dayLabel);

                    // Check if this is today
                    if (dateStr === todayDateStr) {
                        dayCell.classList.add('today');
                    }

                    const dayData = history[dateStr];

                    if (dayData) {
                        let totalStars = 0;
                        let completedTasks = 0;

                        // For today, use real-time data to match the top summary
                        if (dateStr === todayDateStr) {
                            // Use real-time calculation for today to match updateStats()
                            for (const task of this.tasks) {
                                const taskConfig = this.taskLevels[task];
                                if (taskConfig && taskConfig.activities) {
                                    let hasAnyStars = false;
                                    let taskStars = 0;

                                    // Check each activity to see if any has stars and sum up the stars
                                    for (const activityId of Object.keys(taskConfig.activities)) {
                                        try {
                                            const response = await fetch(`/api/user/${this.currentUser}/task/${task}/activity/${activityId}/status`);
                                            if (response.ok) {
                                                const activityData = await response.json();
                                                if (activityData.level && activityData.level > 0) {
                                                    hasAnyStars = true;
                                                    taskStars += activityData.level;
                                                }
                                            }
                                        } catch (error) {
                                            console.error(`Error checking activity status for ${task}/${activityId}:`, error);
                                        }
                                    }

                                    totalStars += taskStars;

                                    if (hasAnyStars) {
                                        completedTasks++;
                                    }
                                }
                            }
                        } else {
                            // For historical days, use cached history data (MAX level per task)
                            this.tasks.forEach(task => {
                                const taskLevel = dayData[task];
                                if (typeof taskLevel === 'number') {
                                    totalStars += taskLevel;
                                    if (taskLevel > 0) {
                                        completedTasks++;
                                    }
                                }
                            });
                        }

                        if (completedTasks === this.tasks.length) {
                            dayCell.classList.add('completed');
                        } else if (totalStars > 0) {
                            dayCell.classList.add('partial');
                        }

                        // Show stars if there are any
                        if (totalStars > 0) {
                            const starsLabel = document.createElement('div');
                            starsLabel.textContent = `${totalStars} ⭐`;
                            starsLabel.style.fontSize = '0.6rem';
                            starsLabel.style.fontWeight = 'bold';
                            starsLabel.style.color = 'white';
                            starsLabel.style.marginTop = '2px';
                            starsLabel.style.textShadow = '0 1px 2px rgba(0,0,0,0.1)';
                            starsLabel.style.lineHeight = '1';
                            starsLabel.style.textAlign = 'center';
                            dayCell.appendChild(starsLabel);
                        } else {
                            // Show empty star for days with data but no completion
                            const starsLabel = document.createElement('div');
                            starsLabel.textContent = '☆';
                            starsLabel.style.fontSize = '0.8rem';
                            starsLabel.style.color = '#9ca3af';
                            starsLabel.style.marginTop = '2px';
                            starsLabel.style.textAlign = 'center';
                            dayCell.appendChild(starsLabel);
                        }
                    } else {
                        // Show empty star for days without data
                        const emptyLabel = document.createElement('div');
                        emptyLabel.textContent = '☆';
                        emptyLabel.style.fontSize = '0.8rem';
                        emptyLabel.style.color = '#9ca3af';
                        emptyLabel.style.marginTop = '2px';
                        emptyLabel.style.textAlign = 'center';
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

    /**
     * Create animated background particles
     */
    createParticles() {
        try {
            const particlesContainer = document.getElementById('particles');
            if (!particlesContainer) return;

            const particleCount = 50;
            // Ensure particles stay invisible for at least the first BASE_DELAY seconds
            const BASE_DELAY_SECONDS = 0; // minimum time particles are hidden after initial page load
            const EXTRA_RANDOM_DELAY = 8; // additional random delay spread to avoid a wave effect

            for (let i = 0; i < particleCount; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                // Start each particle after the base invisible period plus a random extra delay
                particle.style.animationDelay = (BASE_DELAY_SECONDS + Math.random() * EXTRA_RANDOM_DELAY) + 's';
                particle.style.animationDuration = (15 + Math.random() * 10) + 's';
                particlesContainer.appendChild(particle);
            }
        } catch (error) {
            console.error('Error creating particles:', error);
        }
    }

    /**
     * Toggle between light and dark theme
     */
    toggleTheme() {
        try {
            const body = document.body;
            const themeToggle = document.getElementById('themeToggle');

            // Disable auto theme when user manually toggles
            localStorage.setItem('autoThemeDisabled', 'true');

            if (body.classList.contains('dark-theme')) {
                body.classList.remove('dark-theme');
                themeToggle.textContent = '🌙';
                localStorage.setItem('theme', 'light');
            } else {
                body.classList.add('dark-theme');
                themeToggle.textContent = '☀️';
                localStorage.setItem('theme', 'dark');
            }
        } catch (error) {
            console.error('Error toggling theme:', error);
        }
    }

    /**
     * Initialize theme from localStorage
     */
    initializeTheme() {
        try {
            const savedTheme = localStorage.getItem('theme');
            const body = document.body;
            const themeToggle = document.getElementById('themeToggle');

            // Check if user has manually overridden auto theme
            const autoThemeDisabled = localStorage.getItem('autoThemeDisabled') === 'true';

            let shouldUseDarkTheme = false;

            if (autoThemeDisabled) {
                // Use saved preference if auto theme is disabled
                shouldUseDarkTheme = savedTheme === 'dark';
            } else {
                // Auto theme based on time (6pm-6am = dark theme)
                const now = new Date();
                const hour = now.getHours();
                shouldUseDarkTheme = hour >= 18 || hour < 6;

                // Save the auto-determined theme
                localStorage.setItem('theme', shouldUseDarkTheme ? 'dark' : 'light');
            }

            if (shouldUseDarkTheme) {
                body.classList.add('dark-theme');
                if (themeToggle) themeToggle.textContent = '☀️';
            } else {
                body.classList.remove('dark-theme');
                if (themeToggle) themeToggle.textContent = '🌙';
            }
        } catch (error) {
            console.error('Error initializing theme:', error);
        }
    }

    /**
     * Update background gradient based on current user
     */
    updateUserBackground(userId = null) {
        try {
            const body = document.body;
            const currentUserId = userId || this.currentUser;

            // Remove all existing user classes
            body.classList.remove('user-alice', 'user-bob', 'user-carol');

            // Add the current user's class
            if (currentUserId) {
                body.classList.add(`user-${currentUserId}`);
            }
        } catch (error) {
            console.error('Error updating user background:', error);
        }
    }

    /**
     * Start automatic theme checking based on time (6pm-6am = dark theme)
     */
    startAutoThemeChecker() {
        // Check theme every minute to catch hour changes
        setInterval(() => {
            this.checkAutoTheme();
        }, 60000); // 60 seconds
    }

    /**
     * Check if theme should be automatically updated based on current time
     */
    checkAutoTheme() {
        try {
            const autoThemeDisabled = localStorage.getItem('autoThemeDisabled') === 'true';

            if (autoThemeDisabled) {
                return; // Don't auto-update if user has manually overridden
            }

            const now = new Date();
            const hour = now.getHours();
            const shouldUseDarkTheme = hour >= 18 || hour < 6;

            const body = document.body;
            const themeToggle = document.getElementById('themeToggle');
            const currentlyDark = body.classList.contains('dark-theme');

            if (shouldUseDarkTheme && !currentlyDark) {
                // Switch to dark theme
                body.classList.add('dark-theme');
                if (themeToggle) themeToggle.textContent = '☀️';
                localStorage.setItem('theme', 'dark');
            } else if (!shouldUseDarkTheme && currentlyDark) {
                // Switch to light theme
                body.classList.remove('dark-theme');
                if (themeToggle) themeToggle.textContent = '🌙';
                localStorage.setItem('theme', 'light');
            }
        } catch (error) {
            console.error('Error in auto theme check:', error);
        }
    }

    /**
     * Re-enable automatic theme switching (useful for settings)
     */
    enableAutoTheme() {
        localStorage.removeItem('autoThemeDisabled');
        this.checkAutoTheme(); // Apply current time-based theme immediately
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