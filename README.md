# 🎬 MediaHub  

**MediaHub** is your personal media server — a lightweight, self-hosted alternative to Plex or Jellyfin.  
Organize, stream, and enjoy your movies, shows, and photos from any device with a clean, responsive web interface. 

---

## ✨ Features  

- 📂 **Library Management**  
  - Organize movies, TV shows, and photos into libraries  
  - Support for folders & subfolders  
  - Automatic posters (optional)  
  - Hiding libraries (e.g. prevent children access to R-rated movies)

- ▶️ **Streaming Player**  
  - Powered by [Video.js](https://videojs.com/) for smooth playback  
  - “Resume Watching” support — pick up where you left off  
  - Choose your own poster image for unsynced libraries  

- 🖼️ **Image Viewing**
  - Photo galleries with [PhotoSwipe](https://photoswipe.com/) lightbox  
  - Mobile-friendly tiles & grid layout  

- 📱 **Mobile Ready**
  - Responsive UI with larger buttons and touch-friendly controls on phones
  - Courtesy of [Bootstrap](https://getbootstrap.com/)

- 🔐 **User Aware**  
  - NOT YET

---

## Disclaimer
Beware, this mediaserver was created for LAN use only, I would not recommend exposing it to the internet unless you really know what you are doing. Additionally making it publicly available IF you are serving copyrighted material will get you in trouble! (keyword piracy) 

---

## 🚀 Getting Started
(at the moment not production setup)

### Requirements  
- Python 3.10+
- Django 5+

### Installation

```bash
# clone repo
git clone https://github.com/yourusername/mediahub.git
cd mediahub

# create virtualenv
python -m venv venv
source venv/bin/activate

# install dependencies
pip install -r requirements.txt

# run migrations
python manage.py migrate

# start server
python manage.py runserver
```

### Configuration
You need a `config.yaml` file in the base directory:

```yaml
libraries:
  - name: Movies
    type: movies
    path: /home/media/movies
    hidden: false
    sync: true

  - name: Family Photos
    type: pictures
    path: /home/media/family
    hidden: false
    sync: false

  - name: Bangkok Trip
    type: pictures
    path: /home/media/bangkok
    hidden: true
    sync: false

hidden_pin: "1234"
```

- `name` ... the name of the library in the GUI
- `type` ... pictures or movies
- `path` ... physical directory path
- `hidden` ... should this library be hidden by default?
- `sync` ... should this library try to use the movie database to gather the original title and poster etc.
- `hidden_pin` ... pin to unlock hidden libraries (4 digits) 

If you want to sync movie posters / titles from a movie database, please visit [TMDB](https://www.themoviedb.org/) and create an account. Copy your API KEY and set it as environment variable.

```bash
export TMDB_API_KEY="..."
```

### Run as Service

`/etc/systemd/system/mediahub.service`:
```
  [Unit]
  Description=MediaHub server
  After=network.target

  [Service]
  User=<your_user>
  Group=<your_user>
  WorkingDirectory=<mediahub_base_directory>
  ExecStart=<mediahub_base_directory>/start-server.sh
  Restart=always
```

`<mediahub_base_directory>/start-server.sh`:
```bash
#!/bin/bash
cd <mediahub_base_directory>
source venv/bin/activate
export TMDB_API_KEY=<your_api_key>
python manage.py runserver 0.0.0.0:8000
```

- `<your_user>` ... the user you want to run the service as
- `<mediahub_base_directory>` ... the repository clone directory
- `<your_api_key>` ... your TMDB API Key