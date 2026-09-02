<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/">
    <html lang="en">
        <head>
            <meta charset="UTF-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <title>NeuraX Sitemap</title>
            <meta name="description" content="XML sitemap for the official NeuraX website."/>
            <style>

                * {
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }

                html {
                    scroll-behavior: smooth;
                }

                body {
                    min-height: 100vh;

                    font-family:
                        Inter,
                        Segoe UI,
                        system-ui,
                        -apple-system,
                        BlinkMacSystemFont,
                        sans-serif;

                    color: #ffffff;

                    background:
                        radial-gradient(
                            circle at 50% -10%,
                            rgba(124, 58, 237, 0.18),
                            transparent 42%
                        ),
                        linear-gradient(
                            180deg,
                            #0a0c10 0%,
                            #07090d 100%
                        );

                    padding: 40px 20px;
                }

                .container {
                    width: min(
                        100%,
                        1000px
                    );

                    margin: 0 auto;
                }

                .hero {
                    padding:
                        50px
                        40px;

                    border:
                        1px solid
                        rgba(255,255,255,0.08);

                    border-radius: 24px;

                    background:
                        linear-gradient(
                            145deg,
                            rgba(18,22,32,0.96),
                            rgba(11,14,20,0.96)
                        );

                    box-shadow:
                        0 30px 80px
                        rgba(0,0,0,0.35),
                        0 0 50px
                        rgba(124,58,237,0.08);

                    text-align: center;

                    margin-bottom: 24px;
                }

                .logo {
                    display: inline-flex;
                    align-items: center;

                    margin-bottom: 18px;

                    font-size: 34px;
                    font-weight: 900;

                    letter-spacing: -1.5px;
                }

                .logo-dot {
                    width: 10px;
                    height: 10px;

                    margin-right: 10px;

                    border-radius: 50%;

                    background: #7c3aed;

                    box-shadow:
                        0 0 12px #7c3aed,
                        0 0 28px
                        rgba(124,58,237,0.6);
                }

                h1 {
                    font-size:
                        clamp(
                            2rem,
                            5vw,
                            3.2rem
                        );

                    line-height: 1.1;

                    margin-bottom: 14px;

                    letter-spacing: -0.04em;

                    background:
                        linear-gradient(
                            135deg,
                            #ffffff,
                            #a78bfa
                        );

                    -webkit-background-clip: text;
                    background-clip: text;

                    -webkit-text-fill-color: transparent;
                }

                .subtitle {
                    max-width: 650px;

                    margin: 0 auto;

                    color: #9ca3af;

                    font-size: 1rem;
                    line-height: 1.7;
                }

                .status {
                    display: inline-flex;
                    align-items: center;

                    gap: 8px;

                    margin-top: 24px;

                    padding:
                        8px
                        14px;

                    border:
                        1px solid
                        rgba(124,58,237,0.25);

                    border-radius: 999px;

                    background:
                        rgba(124,58,237,0.08);

                    color: #c4b5fd;

                    font-size: 0.85rem;
                    font-weight: 700;
                }

                .status-dot {
                    width: 7px;
                    height: 7px;

                    border-radius: 50%;

                    background: #7c3aed;

                    box-shadow:
                        0 0 10px
                        rgba(124,58,237,0.8);
                }

                .card {
                    overflow: hidden;

                    border:
                        1px solid
                        rgba(255,255,255,0.08);

                    border-radius: 20px;

                    background:
                        rgba(18,22,32,0.94);

                    box-shadow:
                        0 20px 50px
                        rgba(0,0,0,0.25);
                }

                .card-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;

                    gap: 15px;

                    padding:
                        18px
                        22px;

                    border-bottom:
                        1px solid
                        rgba(255,255,255,0.07);

                    background:
                        rgba(255,255,255,0.025);
                }

                .card-title {
                    font-size: 1rem;
                    font-weight: 800;
                }

                .count {
                    padding:
                        5px
                        10px;

                    border-radius: 999px;

                    background:
                        rgba(124,58,237,0.12);

                    color: #c4b5fd;

                    font-size: 0.78rem;
                    font-weight: 800;
                }

                .url-list {
                    display: grid;

                    gap: 12px;

                    padding: 18px;
                }

                .url-item {
                    padding: 18px;

                    border:
                        1px solid
                        rgba(255,255,255,0.07);

                    border-radius: 14px;

                    background:
                        rgba(255,255,255,0.02);

                    transition:
                        transform 180ms ease,
                        border-color 180ms ease,
                        background 180ms ease;
                }

                .url-item:hover {
                    transform: translateY(-2px);

                    border-color:
                        rgba(124,58,237,0.4);

                    background:
                        rgba(124,58,237,0.05);
                }

                .url-label {
                    margin-bottom: 8px;

                    color: #6b7280;

                    font-size: 0.72rem;
                    font-weight: 800;

                    text-transform: uppercase;

                    letter-spacing: 0.08em;
                }

                .url {
                    display: block;

                    overflow-wrap: anywhere;

                    color: #c4b5fd;

                    font-size: 0.95rem;
                    font-weight: 700;

                    line-height: 1.6;

                    text-decoration: none;
                }

                .url:hover {
                    color: #a78bfa;
                }

                .lastmod {
                    margin-top: 8px;

                    color: #6b7280;

                    font-size: 0.8rem;
                }

                footer {
                    margin-top: 24px;

                    color: #4b5563;

                    font-size: 0.8rem;

                    text-align: center;
                }

                footer a {
                    color: #7c3aed;

                    text-decoration: none;
                }

                footer a:hover {
                    color: #a78bfa;
                }

                @media (max-width: 600px) {

                    body {
                        padding: 20px 12px;
                    }

                    .hero {
                        padding:
                            35px
                            20px;
                    }

                    .logo {
                        font-size: 28px;
                    }

                    .card-header {
                        align-items: flex-start;
                        flex-direction: column;
                    }

                    .url-list {
                        padding: 12px;
                    }
                }
            </style>
        </head>
        <body>
            <main class="container">
                <section class="hero">
                    <div class="logo">
                        <span class="logo-dot"></span>
                        NeuraX
                    </div>
                    <h1>
                        XML Sitemap
                    </h1>
                    <p class="subtitle">
                        This sitemap contains the canonical
                        URLs available for search-engine
                        discovery on the NeuraX website.
                    </p>
                    <div class="status">
                        <span class="status-dot"></span>
                        Sitemap is active
                    </div>
                </section>
                <section class="card">
                    <div class="card-header">
                        <div class="card-title">
                            Indexed URLs
                        </div>
                        <div class="count">
                            <xsl:value-of select="count(s:urlset/s:url)"/>
                            URL
                        </div>
                    </div>
                    <div class="url-list">
                        <xsl:for-each select="s:urlset/s:url">
                            <article class="url-item">
                                <div class="url-label">
                                    Website URL
                                </div>
                                <a class="url" href="{s:loc}">
                                    <xsl:value-of select="s:loc"/>
                                </a>
                                <xsl:if test="s:lastmod">
                                    <div class="lastmod">
                                        Last modified:
                                        <xsl:value-of select="s:lastmod"/>
                                    </div>
                                </xsl:if>
                            </article>
                        </xsl:for-each>
                    </div>
                </section>
                <footer>
                    NeuraX Sitemap.
                    <a href="https://dytalmc.github.io">
                        Visit Website
                    </a>
                </footer>
            </main>
        </body>
    </html>
</xsl:template>
</xsl:stylesheet>
