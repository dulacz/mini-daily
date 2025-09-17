# Mini Daily - Personal Wellness Tracker

A modern, lightweight web application for tracking daily wellness activities. Built with FastAPI and vanilla JavaScript, designed for personal use with no authentication required. Perfect for tracking habits across multiple users on the same network.

## ✨ Key Features

### 🏠 **Multi-User Support**
- **Family-friendly**: Support for multiple users (Alice, Bob, Carol by default)
- **User switching**: Easy user tabs to switch between different user profiles  
- **Individual progress**: Each user has their own tasks, progress tracking, and history
- **Customizable user configs**: Each user can have different tasks and activity types

### 📋 **Flexible Task Management** 
- **Hierarchical structure**: Tasks → Activities → Levels (1-3 stars)
- **Multiple activities per task**: Each task can have several sub-activities
  - Example: "Fitness" task includes Walking, Workout, and Yoga activities
- **Star-based rating**: 3-level completion system (1, 2, or 3 stars per activity)
- **Daily tracking**: Track completion status for each day

### 📊 **Progress Visualization**
- **Real-time dashboard**: Live progress circle showing daily completion percentage
- **Streak tracking**: Consecutive day streaks with fire emoji counter
- **Star accumulation**: Total star count across all activities and days  
- **Monthly calendar grid**: Visual month view showing completion status
  - 🟢 Green: All tasks completed (3/3)
  - 🟡 Yellow: Partial completion (some tasks done)
  - ⚪ Gray: No tasks completed

### 🎨 **Modern User Experience**
- **Responsive design**: Works seamlessly on desktop, tablet, and mobile
- **Dark/Light themes**: Toggle between themes with animated transitions
- **Animated backgrounds**: Beautiful particle effects that adapt to theme
- **User-specific themes**: Each user can have personalized background gradients
- **Achievement system**: Celebratory popups for milestones

### 🔧 **Technical Features**
- **No authentication**: Simple, privacy-focused local usage
- **Network accessible**: Access from any device on your local network
- **SQLite storage**: Lightweight, file-based database
- **Real-time updates**: Live progress updates without page refreshes
- **RESTful API**: Modern API endpoints for all functionality
- **Progressive Web App ready**: Optimized for mobile usage

### 📱 **Default Task Categories**
The app comes pre-configured with wellness-focused tasks:

**📚 Knowledge** (Learning & Growth)
- Reading books/articles
- Watching documentaries  
- Listening to audiobooks/podcasts

**💪 Fitness** (Physical Health)
- Walking/hiking
- Structured workouts
- Yoga/stretching

**🎨 Creativity** (Mental Wellness)
- Writing/journaling
- Art/creative projects
- Music/creative expression

## 🚀 Quick Start
```powershell
# Clone and setup
git clone <repository-url>
cd mini-daily

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 📱 Access from Mobile
1. Run `ipconfig` to find your computer's IPv4 address
2. Open `http://<YOUR-IP>:8000/` on your phone/tablet
3. Bookmark for easy daily access

## ⚙️ Configuration

### Customize Tasks and Activities
Edit `data/users.yaml` to customize:
- User names and themes
- Task categories and descriptions  
- Activities within each task
- Star level descriptions (1-3 star meanings)

Example configuration:
```yaml
users:
  alice:
    name: "Alice"
    color: "#6366f1"
    tasks:
      knowledge:
        title: "Knowledge"
        icon: "📚"
        activities:
          reading:
            label: "Reading"
            levels:
              1: "1 chapter"
              2: "30 minutes reading"  
              3: "1 hour deep reading"
```

### Add New Users
Simply add new user configurations to `data/users.yaml` and restart the server.

## 💾 Data Management

### Storage Location
- **Database**: `data/checkins.db` (SQLite)
- **Configuration**: `data/users.yaml` 
- **Backup**: Copy both files to preserve all data and settings

### Data Structure
- Tracks daily completion levels for each user-task-activity combination
- Preserves historical data for streak calculations and monthly views
- Stores optional notes for each task completion

## 🧪 Testing
```powershell
pytest -q
```

## 🎯 Perfect For
- **Personal habit tracking**: Build consistent daily routines
- **Family wellness**: Track habits for multiple family members
- **Goal achievement**: Visual progress tracking motivates consistency  
- **Privacy-conscious users**: No cloud storage, no accounts, no tracking
- **Local network usage**: Perfect for home/office environments

## 🔮 Architecture
- **Backend**: FastAPI (Python) - Modern, fast web framework
- **Frontend**: Vanilla JavaScript - No framework dependencies, lightweight
- **Database**: SQLite - Simple, reliable, file-based storage
- **Styling**: Modern CSS with custom properties and responsive design
- **Testing**: Pytest with FastAPI TestClient

## 📈 Roadmap
- ✅ Multi-user support
- ✅ Hierarchical task structure
- ✅ Monthly progress calendar
- ✅ Dark/light theme switching
- ✅ Responsive mobile design
- ✅ Achievement system
- 🔲 CSV export functionality
- 🔲 Data visualization charts
- 🔲 Web-based configuration editor
- 🔲 Progressive Web App (PWA) features

