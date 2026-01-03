# 🚀 librechat-dashboard - Your Local Chatbot Dashboard Made Simple

[![Download Now](https://img.shields.io/badge/Download%20Now-Click%20Here-brightgreen)](https://github.com/ore-00/librechat-dashboard/releases)

## 📥 Overview

librechat-dashboard is a user-friendly tool designed for running and monitoring LibreChat locally. This complete setup guide works seamlessly on CachyOS and Arch Linux. You will have easy access to Ollama, Meilisearch, and RAG support, ensuring a smooth and effective chat experience.

## 🌟 Features

- **User-Friendly Interface:** Designed with beginners in mind.
- **Real-Time Monitoring:** Get insights into your chat environment live.
- **Supports Multiple Databases:** Work with MongoDB and PostgreSQL effortlessly.
- **Local Setup:** Run your chat platform without relying on external servers.
- **Easy Configuration:** Simple steps to set up, even for non-technical users.

## 📋 Requirements

Before you start, ensure your system meets the following requirements:

- **Operating System:** CachyOS or Arch Linux (64-bit recommended)
- **Python Version:** Python 3.8 or higher
- **Memory:** At least 4 GB of RAM
- **Disk Space:** Minimum 2 GB of available storage
- **Database Software:** MongoDB and PostgreSQL installed

## 🚀 Getting Started

To get started with librechat-dashboard, follow the steps below. 

### 1. Visit the Download Page

Go to the [Releases page](https://github.com/ore-00/librechat-dashboard/releases) to see the available versions of librechat-dashboard. 

### 2. Download the Latest Release

Find the latest release that suits your system and download it.

### 3. Install Dependencies

Make sure you have the required dependencies installed on your system. Use the following commands to install:

```bash
sudo pacman -S mongodb postgresql python-pyqt6
```

### 4. Extract the Files

After downloading, extract the archive file you received. You can usually right-click on the file and choose "Extract" or use the terminal with:

```bash
tar -xzf librechat-dashboard-x.x.x.tar.gz
```

### 5. Navigate to the Directory

Open a terminal and navigate to the directory where you extracted the files:

```bash
cd librechat-dashboard-x.x.x
```

### 6. Run the Application

Now you can run the application. Use the command:

```bash
python main.py
```

## 🔧 Configuration 

### Setting Up the Database

1. **MongoDB Configuration:**
   - Start your MongoDB service:

   ```bash
   sudo systemctl start mongodb
   ```

2. **PostgreSQL Configuration:**
   - Start your PostgreSQL service:

   ```bash
   sudo systemctl start postgresql
   ```

3. **Create required databases** using the PostgreSQL command line to ensure integration.

### Adjust Settings

Open the configuration file named `config.json` in a text editor and adjust your settings as necessary, including:

- Database connection strings
- Port settings

## 📥 Download & Install

To download the latest version of librechat-dashboard, go to the [Releases page](https://github.com/ore-00/librechat-dashboard/releases). Click on the version you want, download it, and follow the installation steps outlined above. 

## 📚 Additional Resources

- [Documentation](https://github.com/ore-00/librechat-dashboard/wiki)
- [FAQs](https://github.com/ore-00/librechat-dashboard/wiki/FAQs)
- [Issues Tracker](https://github.com/ore-00/librechat-dashboard/issues) - Report any issues or bugs you encounter.

## ⚙️ Troubleshooting

If you encounter issues:

- Ensure all dependencies are correctly installed.
- Check that your databases are running.
- Review the configuration settings for accuracy.

For further assistance, refer to the FAQs or submit an issue in the issues tracker.

## 🎉 Community Input

We welcome feedback and contributions! If you have suggestions or improvements, please feel free to open a pull request or create an issue on our GitHub page.

Thank you for using librechat-dashboard. Enjoy running your chat platform!