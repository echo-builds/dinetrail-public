<p align="right">
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

# DineTrail

> A travel dining companion that remembers your entire meal.

https://github.com/user-attachments/assets/54187ea3-4499-4ec5-b2ce-d4222a4fd377

## What DineTrail Does

Photograph a menu one page at a time, and browse, ask, and choose as you go.

DineTrail keeps track of everything you have selected throughout the meal, matches dishes with recommendations from the Xiaohongshu posts you bring, and goes beyond translation with flavor and texture cues while flagging potential deal-breakers.

Instead of ending up with a stack of translated menu pages, you get a complete order you can show directly to the server.

## Why DineTrail

While traveling in Europe, I found that ordering at a restaurant rarely means photographing the entire menu, waiting for every page to be translated, and then choosing from dozens of dishes all at once. Menus are often long. People usually browse one page, ask about a few dishes, pick one or two, and then move on to the next.

Ordering rarely starts from scratch either. Travelers often arrive with Xiaohongshu recommendations saved beforehand, only to hunt for the same dishes again on a menu in an unfamiliar language.

And even after a dish name is translated, you may still not know whether it is raw, contains offal, or tastes nothing like you expected.

That is why DineTrail is organized around an entire meal rather than a single menu page. It keeps your guides, menu pages, questions, and selections together until the order is complete.

## Run Locally

Clone the repository and copy the environment file:

```bash
git clone https://github.com/echo-builds/dinetrail-public.git
cd dinetrail-public
cp .env.example .env
```

Add your Alibaba Cloud Model Studio API key to `.env`:

```text
DASHSCOPE_API_KEY=your_key
```

Start the server:

```bash
python3 server.py
```

Open `http://localhost:4173`. The interface will load without an API key, but real menu recognition and chat will be unavailable.

## Developer Documentation

- [Deployment Guide](docs/DEPLOYMENT.en.md)
- [Real-Menu Evaluation](docs/EVALUATION.en.md)

## License

This project is released under the [MIT License](LICENSE). You may use, modify, and redistribute it as long as you retain the original copyright and license notice.
