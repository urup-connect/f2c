# F2C Cannabis | Cultivators' Collective
## Development Plan & Product Roadmap

---

# Project Objectives

## Business Goals

- Create a membership-based cultivator community.
- Enable members to discover and purchase plants.
- Facilitate plant swapping between members.
- Generate recurring revenue through subscriptions.
- Build trust through reviews and ratings.
- Provide self-service support functionality.

---

# Phase 0: Discovery & Architecture

**Duration:** 1-2 Weeks

## Requirements & Analysis

- [ ] Finalize business requirements.
- [ ] Define membership tiers and benefits.
- [ ] Define subscription model and pricing.
- [ ] Define plant ownership lifecycle.
- [ ] Define harvest and fulfilment workflow.
- [ ] Define SwapZone processes and rules.
- [ ] Define review and leaf rating systems.

## Technical Design

- [ ] Design application architecture.
- [ ] Design database schema.
- [ ] Select authentication strategy.
- [ ] Select payment gateway.
- [ ] Define hosting and infrastructure requirements.
- [ ] Define security and compliance requirements.

## Deliverables

- [ ] Product Requirements Document (PRD)
- [ ] Database ERD
- [ ] UX Wireframes
- [ ] Technical Architecture Document

---

# Phase 1: MVP Foundation

**Duration:** 3-4 Weeks

## Epic: Public Website

### Landing Page

- [ ] Create homepage.
- [ ] Add intro blurb.
- [ ] Add introduction video.
- [ ] Add membership information.
- [ ] Add plant snapshot section.
- [ ] Add terms and conditions.
- [ ] Add community rules.
- [ ] Display membership fees.
- [ ] Add sign-up call-to-action.

### Product Categories

- [ ] Billing category page
- [ ] Fruit category page
- [ ] Vegetables category page
- [ ] Nuts category page
- [ ] Dried category page
- [ ] Honey category page
- [ ] Cannabis category page

## Epic: Authentication

### Registration

- [ ] User registration.
- [ ] Email verification.
- [ ] Password creation.

### Login

- [ ] Login functionality.
- [ ] Logout functionality.
- [ ] Password reset.

## Epic: User Profile

### Profile Management

- [ ] View profile.
- [ ] Edit profile.
- [ ] Manage nickname.
- [ ] Manage email.
- [ ] Manage contact number.
- [ ] Manage delivery addresses.

## Deliverables

- [ ] Public marketing website
- [ ] User registration
- [ ] User authentication
- [ ] Profile management

---

# Phase 2: Plantation Marketplace

**Duration:** 3-5 Weeks

## Epic: Plantation

### Plant Listings

- [ ] Display available plants.
- [ ] Plant detail pages.
- [ ] Plant availability management.

### Search & Filtering

- [ ] Filter by strain.
- [ ] Filter by cultivator.
- [ ] Filter by estimated harvest date.
- [ ] Filter by rating.
- [ ] Filter by top sales.
- [ ] Filter by price.

### Promotions

- [ ] Featured plants section.
- [ ] Special offers section.

## Epic: Ordering

### Purchase Workflow

- [ ] Add plant to order.
- [ ] Checkout process.
- [ ] Order confirmation.
- [ ] Order history.

## Deliverables

- [ ] Functional plant marketplace
- [ ] Search and filtering
- [ ] Order management

---

# Phase 3: Memberships & Payments

**Duration:** 2-3 Weeks

## Epic: Memberships

### Subscription Management

- [ ] Create subscription plans.
- [ ] Subscribe to membership.
- [ ] Upgrade membership.
- [ ] Cancel subscription.
- [ ] Manage renewals.

## Epic: Payments

### Payment Processing

- [ ] Integrate payment gateway.
- [ ] Store payment methods.
- [ ] Process payments.
- [ ] Payment history.

### Financial Records

- [ ] Generate invoices.
- [ ] Generate receipts.
- [ ] Transaction logging.

## Deliverables

- [ ] Subscription revenue model
- [ ] Automated billing
- [ ] Payment processing

---

# Phase 4: My Plants

**Duration:** 2-3 Weeks

## Epic: Plant Portfolio

### Plant Ownership Dashboard

- [ ] View owned plants.
- [ ] View plant status.
- [ ] View purchase history.
- [ ] View subscription orders.

### Order Fulfilment

- [ ] Confirm orders.
- [ ] Select final product type.
- [ ] Confirm delivery address.
- [ ] Capture final payment.

## Deliverables

- [ ] My Plants dashboard
- [ ] Plant ownership tracking
- [ ] Fulfilment workflow

---

# Phase 5: Reviews & Reputation

**Duration:** 1-2 Weeks

## Epic: Reviews

### Review Management

- [ ] Submit reviews.
- [ ] View reviews.
- [ ] Edit reviews.
- [ ] Delete reviews.

## Epic: Leaf Rating System

### Rating Features

- [ ] User ratings.
- [ ] Plant ratings.
- [ ] Cultivator ratings.
- [ ] Rating calculation engine.

## Deliverables

- [ ] Community review system
- [ ] Reputation scoring system

---

# Phase 6: Notifications

**Duration:** 1-2 Weeks

## Epic: Notification Center

### Event Notifications

- [ ] New order notifications.
- [ ] Payment notifications.
- [ ] Subscription notifications.
- [ ] Swap request notifications.
- [ ] Support response notifications.

### Notification Channels

- [ ] In-app notifications.
- [ ] Email notifications.

## Deliverables

- [ ] Notification centre
- [ ] Automated messaging

---

# Phase 7: SwapZone

**Duration:** 4-6 Weeks

## Epic: Plant Swaps

### Swap Listings

- [ ] Create swap listings.
- [ ] Browse available swaps.
- [ ] Search swap listings.

### Swap Workflow

- [ ] Request swap.
- [ ] Accept swap.
- [ ] Reject swap.
- [ ] Cancel swap.

### Approval Process

- [ ] Member validation.
- [ ] Swap confirmation workflow.
- [ ] Swap audit trail.

### Swap Ratings

- [ ] Rate swap experiences.
- [ ] Update leaf ratings from swaps.

## Deliverables

- [ ] Community swap marketplace
- [ ] Peer-to-peer exchanges
- [ ] Swap reputation system

---

# Phase 8: Support Centre

**Duration:** 1-2 Weeks

## Epic: Support

### Ticketing

- [ ] Create support ticket.
- [ ] Track ticket status.
- [ ] Respond to tickets.

### Self-Service

- [ ] Contact Us page.
- [ ] Rules and Guidelines page.
- [ ] FAQ section.

## Deliverables

- [ ] Support portal
- [ ] Help centre
- [ ] Ticket tracking

---

# Phase 9: Admin Portal

**Duration:** 3-4 Weeks

## Epic: Member Administration

### User Management

- [ ] View members.
- [ ] Edit members.
- [ ] Suspend members.
- [ ] Reinstate members.

### Subscription Management

- [ ] Manage subscriptions.
- [ ] Process refunds.
- [ ] Review payment history.

## Epic: Plantation Administration

### Inventory Management

- [ ] Create plant listings.
- [ ] Update plant listings.
- [ ] Manage availability.
- [ ] Manage promotions.

## Epic: Swap Administration

### Oversight

- [ ] Review swap activity.
- [ ] Handle disputes.
- [ ] Moderate listings.

## Epic: Reporting

### Business Analytics

- [ ] Revenue dashboard.
- [ ] Membership dashboard.
- [ ] Plant sales dashboard.
- [ ] Swap activity dashboard.

## Deliverables

- [ ] Administrative dashboard
- [ ] Reporting suite
- [ ] Operational management tools

---

# Recommended Technology Stack

## Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS

## Backend

- ASP.NET Core Web API
- Entity Framework Core

## Database

- PostgreSQL

## Authentication

- Microsoft Entra ID B2C
- Auth0 (alternative)

## Payments

- PayFast
- PayGate
- Stripe (if business rules permit)

## Infrastructure

- Azure App Services
- Azure PostgreSQL
- Azure Storage Accounts
- Azure Key Vault
- Azure Application Insights

---

# Release Plan

## Release 1

- Landing Page
- Registration
- Login
- User Profile

## Release 2

- Plantation Marketplace
- Plant Browsing
- Ordering

## Release 3

- Memberships
- Payments
- Subscription Management

## Release 4

- My Plants Dashboard
- Ownership Tracking
- Fulfilment Workflow

## Release 5

- Reviews
- Leaf Ratings
- Reputation System

## Release 6

- Notifications
- Email Communications

## Release 7

- SwapZone
- Swap Approval Workflow
- Swap Ratings

## Release 8

- Support Centre
- FAQ
- Ticketing

## Release 9

- Admin Portal
- Reporting
- Operational Management

---

# MVP Definition

The minimum viable product should include:

- [ ] Landing page
- [ ] Member registration
- [ ] Login and authentication
- [ ] Profile management
- [ ] Plantation marketplace
- [ ] Ordering workflow
- [ ] Payment integration
- [ ] Membership subscriptions

**Target MVP Release:** End of Phase 3

This provides the first revenue-generating version of the platform while deferring advanced community functionality (SwapZone, ratings, support systems) until user adoption and business validation have been achieved.