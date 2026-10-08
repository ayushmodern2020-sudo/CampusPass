# CampusPass — Figma-first redesign guide

This refresh uses a deliberately editorial campus aesthetic instead of a generic dashboard template. The implementation in `templates/` + `static/style.css` is the code version of the same design language.

## Direction

- Mood: campus magazine / event poster / modern student union
- Avoid: oversized gradients, excessive pill UI, glassmorphism, repetitive rounded cards
- Surface: warm paper `#F6F2E9`
- Ink: `#182229`
- Navy: `#183544`
- Teal: `#246A65`
- Coral: `#D65B3E`
- Yellow accent: `#E8C35A`
- Lines: `#D8D0C2`
- Card: `#FFFDF8`
- Body font: Inter/system UI
- Display headings: Georgia/serif

## Figma frames

Create frames at 1440×1024 for desktop and 390×844 for mobile.

Pages to design:
1. Student Login
2. Student Registration
3. Events
4. Event Detail / Reserve
5. My Tickets
6. Ticket / QR Pass
7. Booking Success
8. Organizer Login
9. Organizer Dashboard
10. Create Event

## Core components

- Wordmark + square CP mark
- Primary / quiet button
- Section kicker
- Event card
- Ticket row
- Status label
- Fact grid
- Form field
- QR ticket pass
- Organizer stat strip
- Scanner panel

## Layout rules

Use 8px spacing increments, thin 1px borders, and mostly 6–10px corner radii. Let typography and whitespace create hierarchy instead of shadows. Use asymmetric two-column layouts where appropriate.

## How to use this with Figma

1. Import the screenshots of the running pages into Figma as visual references.
2. Recreate the frames/components using the tokens above.
3. Use Auto Layout for cards/forms and a 12-column desktop grid.
4. Keep the exact copy/labels from the code so the design maps one-to-one to the Flask templates.
5. Export only any image assets you decide to add; the current implementation intentionally works without external image dependencies.

The repo cannot generate a native `.fig` file here, but the code and design token sheet are aligned so a Figma file can be recreated directly and then handed back to the same CSS/templates without changing backend behavior.
