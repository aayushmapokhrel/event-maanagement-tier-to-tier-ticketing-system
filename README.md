# Event Management & Multi-tier Ticketing System

A Django-based web application for managing events and selling tickets with multiple pricing tiers. The system includes features like QR code-based check-in, Khalti payment integration, and email notifications.

## Features

- User Authentication & Roles (Organizer, Attendee, Admin)
- Event Creation & Management
- Multi-tier Ticketing System
- QR Code Generation for Tickets
- Khalti Payment Integration
- Email Notifications
- Event Reviews & Ratings
- Social Media Sharing
- Responsive Design

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd event-management-system
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv myvenv
   source myvenv/bin/activate  # On Windows: myvenv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add the following configurations:
   ```
   SECRET_KEY=your-secret-key
   DEBUG=True

   KHALTI_SECRET_KEY=your-khalti-secret-key
   KHALTI_PUBLIC_KEY=your-khalti-public-key

   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-email-password
   ```

5. Run migrations:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

7. Run the development server:
   ```bash
   python manage.py runserver
   ```

8. Visit `http://127.0.0.1:8000/` in your browser.

## Project Structure

```
event_management/
├── events/                 # Main app directory
│   ├── migrations/        # Database migrations
│   ├── templatetags/      # Custom template tags
│   ├── admin.py          # Admin interface configuration
│   ├── forms.py          # Form definitions
│   ├── models.py         # Database models
│   ├── urls.py           # URL patterns
│   └── views.py          # View functions
├── templates/             # HTML templates
│   ├── base.html         # Base template
│   └── events/           # Event-specific templates
├── static/               # Static files (CSS, JS, images)
├── media/                # User-uploaded files
├── manage.py             # Django management script
└── requirements.txt      # Project dependencies
```

## Usage

1. Register as a user
2. Create events (as an organizer)
3. Add ticket tiers to events
4. Purchase tickets (as an attendee)
5. Generate QR codes for check-in
6. Review past events

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Django Framework
- Bootstrap
- Font Awesome
- Khalti Payment Gateway 