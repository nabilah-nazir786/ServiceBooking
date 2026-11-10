# Cousins Car Care - Complete Workflow Documentation

Welcome to the **Cousins Car Care** Service Booking Application. This document outlines the complete workflow and interactions for both Customers (Users) and Workshop Managers (Admins).

## 1. Customer (User) Workflow

### 1.1 Registration & Authentication
* **Sign Up:** New customers register with a Username, Full Name, Email, Phone Number, and Password. Robust validation ensures strong passwords and valid contact details.
* **Log In:** Customers log in to access their personalized dashboard. 
* **Profile Management:** Customers can edit their profile details or change their password directly from their dashboard.

### 1.2 Booking a Service
* **Service Selection:** Users browse active services offered by the workshop and select one or more services.
* **Date & Time Selection:** 
  * Users pick a preferred date.
  * The system dynamically fetches available time slots based on the workshop's operating hours and holiday schedule.
  * **Constraint:** For same-day bookings, the system only allows selecting time slots that are strictly in the future (past timeslots are disabled).
* **Vehicle Details:** Users input their vehicle model and vehicle number. The system remembers previously used vehicles for quick selection.
* **Payment Preference:** Users select their payment method:
  * **Pay Now (Online):** Generates a dynamic UPI QR Code.
  * **Pay After Service:** Allows payment in cash or card at the workshop.

### 1.3 Online Payment & Verification
* **QR Code & UTR:** If "Pay Now" is selected, the user scans the provided UPI QR Code.
* **Proof Upload:** The user must enter the 12-digit UTR (Transaction ID) and upload a screenshot of the successful payment.
* **Verification Status:** The booking enters a `PENDING_VERIFICATION` payment status until the Admin reviews the uploaded proof.

### 1.4 Active Booking Dashboard
* **Live Stepper:** Users can track the real-time progress of their booking via a 4-step progress bar:
  1. **Submitted** (Pending Approval)
  2. **Approved** (Accepted by Admin)
  3. **In Service** (Work has started)
  4. **Completed** (Service finished)
* **Actionable Items:** Users can view full booking details, re-upload payment proof if required, or cancel their booking (only allowed *before* the scheduled service date).

### 1.5 Completion & Feedback
* **Review Gate:** Once a service is marked `COMPLETED` by the Admin, it remains on the user's active dashboard until they leave feedback.
* **Submit Feedback:** The user rates the service (1-5 stars) and leaves a comment.
* **History Archive:** Upon submitting feedback, the booking is moved to the user's "Past Booking History".

---

## 2. Admin (Workshop Manager) Workflow

### 2.1 Dashboard & Overview
* **Key Metrics:** The Admin Dashboard displays high-level KPIs: Total Bookings, Pending Approvals, Today's Ongoing Work, and Total Revenue.
* **Recent Activity:** Admins see a consolidated view of all recent bookings and user activity.

### 2.2 Booking Management
* **Status Updates:** Admins review incoming bookings and update their status (`PENDING` â `APPROVED` â `IN_PROGRESS` â `COMPLETED`).
* **Payment Verification:** Admins review uploaded transaction screenshots and UTRs to mark payments as `PAID_ONLINE`.
* **Modifications:** Admins can add "Additional Charges" for extra work discovered during the service, and leave internal "Admin Remarks".
* **Manual Booking:** Admins can manually create a booking on behalf of walk-in customers or over the phone.

### 2.3 Service & Schedule Management
* **Service Menu:** Admins can add new services, edit existing ones (name, description, base price, image), and toggle their visibility.
* **Time Slots:** Admins manage the workshop's operating schedule:
  * Create recurring daily or weekday time slots.
  * Define max capacity (vehicles per slot).
  * Block out specific dates or recurring days as "Holidays / Closed Days" to prevent customer bookings.

### 2.4 Announcements & Gallery
* **Promotions:** Admins can post announcements and promotional banners with specific start and end dates. These are displayed prominently on the customer home page.
* **Gallery:** Admins manage the public-facing gallery showcasing past work, which is displayed in a marquee on the homepage.

### 2.5 Feedback Management
* **Review Moderation:** Admins can view all customer feedback, ratings, and comments.
* **Visibility Control:** Admins have the ability to toggle whether specific feedback is visible publicly.

---

## 3. System Architecture & Validation Rules

* **Time Constraints:** Customers cannot book time slots that have already passed on the current day.
* **Capacity Limits:** Time slots automatically become unavailable once they hit the Admin-defined `max_bookings` limit.
* **Data Formatting:** Vehicle numbers are automatically sanitized and capitalized.
* **Secure Access:** Decorators and middleware ensure that Users cannot access Admin routes, and vice-versa.
