# Quant Course — Arbitrage Pricing & Derivatives

**First edition, 2026.**

Copyright © 2026 Alan. All rights reserved.

No part of this publication may be reproduced, distributed, or transmitted in any form or by any means, including photocopying, recording, or other electronic or mechanical methods, without the prior written permission of the author, except in the case of brief quotations embodied in critical reviews and certain other non-commercial uses permitted by copyright law.

ISBN: [pending — to be assigned at publication]

Printed and bound on demand.

The author has used best efforts in preparing this book, but makes no representations or warranties with respect to the accuracy or completeness of its contents. The examples, case studies, and numerical results are for educational purposes only and do not constitute financial advice or a recommendation to trade any particular instrument. Readers should consult qualified professionals before acting on any information contained herein.

\newpage

## Preface

This is a self-study guide to arbitrage pricing and derivatives, written for a reader who has finished an undergraduate sequence in probability and real analysis and now wants a single coherent path from the math refresher to a senior-quant-grade understanding of pricing and hedging. The reader I had in mind is someone who can follow a clean Itô calculus argument, who has seen the Black–Scholes formula but has never derived it from first principles, and who is allergic to hand-waving. Every result is proved or referenced; every approximation is labelled as such; every case study is grounded in a real episode from the last forty years of derivatives markets.

The sixteen chapters fall into six parts. Chapter 0 collects the prerequisite mathematics — probability, stochastic-process priming, linear algebra, calculus — and is the only chapter every later chapter cites. Part I (Chapters 1–2) develops arbitrage pricing on the binomial tree, where the whole replication-and-measure-change apparatus appears in finite-dimensional form. Part II (Chapters 3–5) builds the continuous-time machinery: Brownian motion, Itô's lemma, the Feynman–Kac bridge, Radon–Nikodym and Girsanov. Part III (Chapters 6–9) applies the machinery to equity derivatives: the Black–Scholes PDE, the Greeks, forwards and futures, Monte Carlo and path-dependent options. Part IV (Chapter 10) is Heston and stochastic volatility. Part V (Chapters 11–14) is rates: calibration, short-rate models, swaps and CDS, caps and swaptions. Part VI (Chapter 15) is the capstone on Value-at-Risk, Expected Shortfall, and coherent risk measures.

A note on the spine. Chapter 3 is the single prerequisite for every chapter from Chapter 4 onwards; its Itô calculus is the working language of the rest of the book. Chapter 5's Girsanov machinery is cited rather than re-derived by Chapters 6, 8, 12, and 13. The $\sigma^2/2$ Jensen-gap correction is introduced in Chapter 0 (§0.2), re-derived from the SDE side in Chapter 3 (§3.10.1a), and reappears in every continuous-time chapter — it is the single most reused fact in the guide. Read §0.2 once carefully and you will stop misremembering the sign.

Real-world case studies appear throughout: Buffett's SPX puts, Black Monday 1987, LTCM 1998, the 2008 crisis, Volmageddon 2018, negative WTI in April 2020, the March 2020 COVID vol surface, Archegos 2021, the UK LDI mini-budget of September 2022, and the Silicon Valley Bank collapse of March 2023. The case studies are not decoration; each one isolates a piece of machinery that the formal argument was building, and shows what happens when the assumption fails. References for every case study appear in the Bibliography at the end of the book.

A note on conventions. Formulas are typeset in LaTeX. Figures live inline next to the concepts they illustrate and were generated from a single Python codebase whose sources are available with the book. Numerical examples are deliberately chosen with simple round numbers so the reader can reproduce them in a spreadsheet or a few lines of Python; the goal is for the arithmetic to be transparent, not to look professional.

How to read this book. Linear front-to-back is the intended path. A reader already comfortable with measure-theoretic probability can skim Chapter 0 and return to it only as needed. A reader whose interest is equity derivatives can stop after Chapter 10; a reader whose interest is fixed income can read Chapters 0–5 then jump to Chapter 12. Chapter 15 is the capstone and assumes most of the prior machinery.

Errata, corrections, and suggestions are welcome.
