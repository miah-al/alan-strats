# Quant-Review Notes

## Review scope

I read the 15 final chapters (CH01–CH15, excluding OLD-* drafts), prioritising the math-dense chapters CH03, CH04, CH05, CH08, CH09, CH10, CH12, CH14, CH15, and spot-reading CH06, CH07, CH11, CH13. Depth varied by chapter: in priority chapters I verified each boxed equation, worked through every numerical example, re-derived the Itô / Feynman-Kac / Girsanov steps from scratch, and traced cross-chapter references. In the lighter chapters (CH01–CH02, CH06–CH07, CH11, CH13, CH15) I verified all boxed formulas, the key derivations, and the numerical worked examples, but read the surrounding prose more cursorily. Every issue flagged below I have verified by explicit (re)derivation or by plugging in numbers.

## Summary

Overall the guide is in strong mathematical shape. The central derivations — Itô's lemma, Feynman-Kac (all three forms), Girsanov, change-of-numeraire, GBM/OU/BM solutions, Black-Scholes PDE, Black-76, Vasicek/Hull-White bond pricing, Heston characteristic function and Riccati ODEs, Jamshidian/Vasicek-Black bond option, and Black-76 caplets — are all correct. I did find three outright technical errors (a wrong covariance matrix in CH03, a spurious "$-\delta$ drift" in CH08, and a dimensionally wrong Student-$t$ ES formula in CH09), a handful of smaller imprecisions, and a few pedagogical rough edges. The errors are localised; none of them propagates to later chapters because the downstream derivations use the formulas correctly, just the presentation at the local spot is off.

## Critical issues

- **[CH03 §3.7.2, line ~477] Wrong covariance matrix for $(W_s, W_t)$.** The text gives the joint law of $(W_s, W_t)$ as Gaussian with covariance matrix $\begin{pmatrix} t & s \\ s & s\end{pmatrix}$ and then writes the correct Cholesky recipe "$W_s = \sqrt{s}Z_1$, $W_t = \sqrt{s}Z_1 + \sqrt{t-s}Z_2$". The recipe gives $\mathrm{Var}(W_s) = s$, $\mathrm{Var}(W_t) = t$, $\mathrm{Cov}(W_s, W_t) = s$ — so the covariance matrix for $(W_s, W_t)$ (in that order, with $s < t$) should be $\begin{pmatrix} s & s \\ s & t\end{pmatrix}$. The diagonal entries are swapped in the printed matrix. **Fix:** replace $\begin{pmatrix}t & s\\ s & s\end{pmatrix}$ with $\begin{pmatrix}s & s\\ s & t\end{pmatrix}$.

- **[CH08 §8.4, eq (8.13b) / unnumbered "case with dividends"] Spurious $-\delta$ drift in forward-price SDE.** After the main result (8.13) that $dF/F = \sigma\,d\widehat W$ is driftless under $\mathbb{Q}$ for the no-dividend case, the "Case with dividends" paragraph claims that for a dividend-paying stock, applying Itô to $F_t(T) = S_t e^{(r-\delta)(T-t)}$ with $dS/S = (r-\delta)\,dt + \sigma\,dW$ gives $dF/F = -\delta\,dt + \sigma\,d\widehat W$. This is wrong. The correct calculation (using $\partial_t F = -(r-\delta)F$, $\partial_S F = F/S$, $\partial_{SS}F = 0$) gives $dF = [-(r-\delta)F + (r-\delta) F]\,dt + \sigma F\,dW = \sigma F\,dW$ — still driftless. Under deterministic rates the forward price of a dividend-paying stock is a $\mathbb{Q}$-martingale, exactly as it is for a non-dividend stock; the $(r-\delta)$-drift of the spot cancels the time-decay of the carry factor. The paragraph then builds an entire misleading story around this phantom $-\delta$ drift ("this is not the futures SDE ... the forward carries a deterministic correction"). **Fix:** delete the "$-\delta$" term and rewrite the paragraph. The distinction the author is reaching for is the forward/futures gap under *stochastic* rates (§8.11's convexity adjustment), not under dividends.

- **[CH09 §9.3, eq (9.6)] Wrong Student-$t$ ES formula — extra VaR factor.** The formula printed is
  $$\mathrm{CTE}_\alpha^{t_\nu} = \mathrm{VaR}_\alpha^{t_\nu} \cdot \frac{\nu + (\mathrm{VaR}_\alpha^{t_\nu})^2}{(\nu-1)\,\alpha} \cdot f_{t_\nu}(\mathrm{VaR}_\alpha^{t_\nu}).$$
  The correct Acerbi-Tasche formula for Student-$t_\nu$ expected shortfall at tail probability $\alpha$ is
  $$\mathrm{ES}_\alpha(t_\nu) = \frac{f_\nu(q_\alpha)}{\alpha}\cdot\frac{\nu + q_\alpha^2}{\nu-1}$$
  where $q_\alpha = \mathrm{VaR}_\alpha$. The printed formula has an extra factor of $\mathrm{VaR}_\alpha$ in front. Plugging in $\nu=3$, $\alpha=0.05$, $q \approx 2.353$: correct ES $\approx 3.88$; printed formula gives $\approx 9.12$; the text quotes $4.19$ which matches neither but is close to the correct value (~8% error, likely rounding of intermediate steps). **Fix:** drop the leading $\mathrm{VaR}_\alpha$ factor from (9.6); keep the numerical value quoted in the surrounding prose (which is roughly correct).

## Minor issues / nits

- **[CH03 §3.4.3] "$\mathrm{Var}(Z^2) = \mathbb{E}[Z^4] - 1 = 3 - 1 = 2$" is missing the centering step.** $\mathrm{Var}(Z^2) = \mathbb{E}[Z^4] - (\mathbb{E}[Z^2])^2 = 3 - 1^2 = 2$; the intermediate "$-1$" is $-(\mathbb{E}[Z^2])^2$, not just $-1$. Not wrong, just elliptical.

- **[CH04 §4.3.5] "The only continuous martingale of finite variation is the zero process."** This needs "starting at zero" to be true as stated (a constant martingale is of finite variation). For the argument used it is fine because the drift integral starts at zero, but the one-liner as printed is technically incomplete — a constant nonzero process is also a bounded-variation continuous martingale.

- **[CH05 §5.1.4–§5.1.5] "Each column is a (sub-)probability distribution ... they disagree on how much probability mass each state deserves".** The subsequent arithmetic ("verifying the change-of-numeraire formula") only works *because* the numbers in the table are Arrow-Debreu state prices rather than actual probabilities — §5.1.4 and §5.1.5 both gesture at this but the wording slides back and forth between "probability" and "state price". A reader trying to reproduce the arithmetic will spend a while debugging "why don't my $\mathbb{Q}$-probabilities sum to 1?" — because they shouldn't, they are state prices. Suggest tightening the language to "state prices (unnormalised probabilities)" throughout §5.1.

- **[CH05 §5.3.2] Mean-one argument for $\eta_t$ is quietly stated only for *deterministic* $\sigma^A$.** "The stochastic integral $\int_0^t \sigma_u^A\,dW_u$ is (when $\sigma^A$ is deterministic) Gaussian..." — the text acknowledges this parenthetically, but the general result that $\eta_t$ is a true martingale for stochastic $\sigma^A$ needs Novikov (§5.3.4), not just the Gaussian MGF. The logic is correct in the text if read carefully, just compressed.

- **[CH08 §8.7] Black-76 rho formula.** The table of Greeks gives $\rho = \partial_r g = -\tau\,g(t,F)$. This is the "business rho" of Black-76 (sensitivity holding $F$ fixed); that is fine for options on exchange-listed futures where $F$ is directly quoted. A reader coming from BS-spot-on-dividend might expect a different sign when they think of $F$ as derived from $S$. A one-line caveat noting "this rho fixes the futures quote, not the spot" would help.

- **[CH08 §8.8.3, "At the money"] Claim "$\Phi(0) = 1/2$ regardless of volatility — a feature unique to the arithmetic-Brownian model".** Literally true that exact $1/2$ is Bachelier-specific; fine.

- **[CH08 §8.9.6, numerical example]** The calculation gives $\Phi(-5/0.0309) \approx \Phi(-162)$. Arithmetic check: $5/0.0309 \approx 161.8$, so $\Phi(-162)$. Correct. The subsequent sentence "In the flat-vol Bachelier model with $\Sigma = 0.20$, $\Phi(-5/0.20) = \Phi(-25)$" is also correct. But the prose calls these "effectively zero" in both cases — this is a bit confusing because the whole point of the example was that the two should price very differently. In fact *both* are effectively zero to machine precision; the comparison is $\Phi(-25) \sim 10^{-138}$ vs. $\Phi(-162) \sim 10^{-5800}$, a ratio the reader cannot feel. A less extreme strike would make the comparison more vivid.

- **[CH10 §10.4.3] Milstein scheme.** The text writes Milstein as $X_n \approx X_{n-1} + \mu\Delta t + \sigma\sqrt{\Delta t} Z_n + \tfrac12 \sigma \sigma' \Delta t (Z_n^2 - 1)$. That's the correct version with $Z_n^2 - 1$ centring (so the correction is mean-zero, preserving the Euler mean). Fine.

- **[CH12 §12.6.3, eq (12.48)–(12.50)] Variance formula.** $\mathbb{V}[\int_0^T r_u\,du] = (\sigma^2/\kappa^2)\int_0^T(1-e^{-\kappa(T-u)})^2\,du \equiv 2 C_T$, with $C_T = (\sigma^2/(2\kappa^2))\int \cdots du$. Correct; the bond price $P_0(T) = \exp(-r_0 B_T - A_T + C_T)$ uses $+\tfrac12 \cdot 2C_T = +C_T$. The worked magnitude ($C_{10} = 0.0084$ for $\sigma=0.01, \kappa=0.1, T=10$) I reproduced — correct to the stated precision.

- **[CH14 §14.8] "Itô isometry turns the sum of squared Brownian increments into a time integral of the squared diffusion coefficient".** Minor mislabelling. What is being invoked is *quadratic variation* (equivalently, the $(dW)^2 = dt$ rule of CH03 §3.4), not the Itô *isometry* (which is the $L^2$ identity for the *variance* of a stochastic integral, CH03 §3.6). Both statements follow from the same underlying fact, but calling the QV identity "Itô isometry" is nonstandard and may confuse careful readers.

- **[CH14 §14.9, Step 1 Riccati numerical check] $d(i)^2 = 4.1275 + 1.65 i$; $d(i) \approx 2.036 + 0.405 i$.** Verified: $(2.036 + 0.405 i)^2 = 2.036^2 - 0.405^2 + 2\cdot 2.036\cdot 0.405 i = 4.145 - 0.164 + 1.649 i = 3.981 + 1.649 i$. Hmm — I get $3.98$ for the real part, text says $4.1275$. Rechecking the computation one step back: $(-0.35i - 2)^2 = 4 + 2\cdot(-0.35 i)\cdot(-2) + 0.1225 i^2 = 4 + 1.4 i - 0.1225 = 3.8775 + 1.4 i$. Then subtract $0.25 i(i-1) = -0.25 - 0.25 i$: $3.8775 + 1.4 i - (-0.25 - 0.25 i) = 4.1275 + 1.65 i$. OK, so $d^2 = 4.1275 + 1.65 i$; but then $d = \sqrt{d^2}$ should satisfy $|d|^2 = \sqrt{4.1275^2 + 1.65^2} = \sqrt{17.04 + 2.72} = \sqrt{19.76} = 4.445$ and $|d| = 2.108$; $\arg d = \tfrac12 \arg(d^2) = \tfrac12 \arctan(1.65/4.1275) = \tfrac12 \cdot 21.78° = 10.89°$, so $d = 2.108 (\cos 10.89° + i\sin 10.89°) = 2.070 + 0.398 i$. Close to the stated $2.036 + 0.405 i$ but not quite. **Small numerical imprecision in CH14's worked Riccati illustration — rounding or a stray digit somewhere; the downstream pricing numerics ($K=90$ → IV 22.4%, etc.) are plausible but I didn't rerun the full Fourier integral.**

- **[CH14 §14.5.3] "Albrecher et al." is the right citation for the "little trap" but Heston's original formula is Heston (1993); a reader might wonder which sign of $d$ is which. The text alludes to this but could be clearer that the printed $g_*$ uses the "minus" branch and that the "little trap" fix is to use the reciprocal.

## Pedagogical suggestions

- **[CH03 §3.5.1] "The classical integral is oblivious to the endpoint choice in the Riemann sum because QV is zero".** Good observation; it would be strengthened by pointing out that this is where the Riemann sum's well-definedness for Riemann-Stieltjes integrals against bounded-variation integrators comes from, making the contrast with Itô sharper.

- **[CH04 §4.3.5, "drift-killing identity"]** The proof uses "a continuous martingale of bounded variation is identically zero". A one-line reminder of *why* (e.g. "quadratic variation of a BV process is zero; a martingale of zero QV is constant; a constant martingale starting at zero is identically zero") would pay for itself immediately.

- **[CH05 §5.4.2, MGF verification]** This is clear, but it would be worth being explicit that the shift direction is: under $\mathbb{Q}^\star$ (not $\mathbb{Q}$), the Brownian has mean $+\sigma$ at $t=1$. A reader who has just absorbed Girsanov as "subtract the integrated volatility from $W$" can get confused by the sign.

- **[CH06 §6.7]** The reading "$x\,\Phi(d_+)$ is the expected stock payoff given that the option expires in the money" is very useful, but is only strictly true if one re-reads it as "expected discounted stock payoff in the share-measure-conditional sense". Spelling out the share-measure/risk-neutral split (which §6.7A does derive) in this paragraph would save later confusion when the same split reappears in CH14's Heston.

- **[CH07] Implicit $q$=0 throughout §7.1–§7.4, then $q \ne 0$ in §7.8.** A reader should be told upfront that the $q$=0 assumption applies in the early worked examples; otherwise the dividend-adjusted Greeks look like they come out of nowhere.

- **[CH08 §8.3, "trio of drifts" table]** This table is great. One improvement: row 3 (futures) should say "under $\mathbb{Q}$" explicitly to distinguish from the forward case in row 4 of a possible extension; as is, the reader has to infer the measure from context.

- **[CH10 §10.5, worked example]** Would benefit from stating the BS answer to four decimals ($10.4506$) so the reader can judge whether their MC estimate is within the quoted standard error.

- **[CH12 §12.4.2]** The derivation "long-bond yield tends to $\theta - \sigma^2/(2\kappa^2)$" is elegant. Could add a one-line algebra cross-check from (12.22) limits: for $T \gg 1/\kappa$, $B_t(T)\to 1/\kappa$ and $A_t(T)\to -\theta(T-1/\kappa) + O(T)$ plus the convexity term; dividing by $T$ and taking $T\to\infty$ gives the stated limit.

- **[CH14 §14.6, $P_1$ vs $P_2$ derivation]** Worth stating explicitly that $P_1$ uses the share-measure $\widetilde{\mathbb{Q}}$ (with $F$ as numeraire) and $P_2$ uses $\mathbb{Q}$. The text does so but in prose; a boxed callout would be nice.

- **[CH15 §15.4b, Bachelier/shifted-Black]** Very good practical section. Could be strengthened by noting that Bachelier vol is in *units of rate per $\sqrt{\text{time}}$* (basis points per $\sqrt{\text{year}}$) — dimensional awareness helps avoid sign/scale confusion.

## Confirmations

- **[CH02]** Verified: multi-period binomial, FTAP I+II derivation, CRR calibration ($p$ and $c$ formulas), risk-neutral $q$ formula (2.22) are correct. American-option early-exercise Bellman equation (2.72) is standard.

- **[CH03]** Verified: QV of BM is $t$ a.s. (3.19); $\int W dW = \tfrac12 W_t^2 - \tfrac12 t$ by both telescoping (3.23) and Itô (3.43); Itô isometry (3.28)-(3.29) with A+B+C proof; Itô's lemma for $f(t,W)$ (3.41) and general $g(t,X)$ (3.47); GBM (3.52), OU/Vasicek (3.55) with variance (3.57), and constant-coefficient BM (3.59). The only slip is the $(W_s, W_t)$ covariance-matrix display (above).

- **[CH04]** Verified: all three Feynman-Kac forms (zero-drift, constant-coefficient with discount, state-dependent), the integrating-factor derivation in §4.9, and the state-dependent theorem (4.34)-(4.36) with its Black-Scholes/Vasicek instantiations. Worked examples (linear, quadratic, exponential) are all correctly derived and PDE-verified.

- **[CH05]** Verified: Radon-Nikodym density formula (5.10); Doléans-Dade exponential (5.22); Girsanov 1D (5.25) and multi-dim (5.31)-(5.32); two-numeraire switch (5.36); change-of-numeraire theorem (5.40); market-price-of-risk density (5.30). MGF verification in §5.4.2 is consistent with the stated Girsanov convention (the mean shift is $+\sigma$ under $\mathbb{Q}^\star$, consistent with $W_t^A = W_t - \int \sigma du$).

- **[CH06]** Verified: generalised BS PDE (6.24); specialisation to GBM (6.27); Black-Scholes call (6.28) and put (6.31); digital (6.32); $\mathbb{E}[X_T^2]$ formula (6.43); market-price-of-risk $\lambda = (\mu - r)/\sigma$.

- **[CH07]** Verified: gamma-hedging setup (7.31–7.40); dividend BS PDE (7.72); Greek tables for call/put.

- **[CH08]** Verified: forward price formula (8.3); futures-as-martingale (8.8); driftless futures SDE under $\mathbb{Q}$ (8.13); self-financing Black PDE derivation (8.24); Black-76 formula (8.30) and numerical check (BS=4.62, B76=3.93 match my computation); Bachelier digital (8.36); Samuelson OU futures (8.38)-(8.43); Margrabe derivation (stated). The only slip is the phantom $-\delta$ drift in the dividend case (above).

- **[CH09]** Verified: VaR definition (9.1), Normal CTE = $\phi(q)/\alpha = 2.06$ at $\alpha=0.05$. The Student-$t$ formula (9.6) has the error above; the stated numerical value ~4.19 is not quite right (my rederivation gives 3.88; both are plausible with rounding).

- **[CH10]** Verified: SLLN/CLT basis; lognormal GBM path generator (10.9); forward-starting call formula (10.26) — I rederived the cancellation of $S_{T_1}$ factors from moneyness.

- **[CH11]** Verified: binomial calibration (11.5)-(11.6); multinomial Radon-Nikodym (11.13)-(11.14); Hull-White $\theta_t$ bootstrap identity.

- **[CH12]** Verified: OU explicit solution (12.12), moments (12.13)-(12.14); integrated rate (12.15)-(12.18); Vasicek bond price (12.19)-(12.22); affine ansatz + Riccati coefficient-matching (12.28)-(12.30); Hull-White generalisation (12.45)-(12.49); convexity adjustment worked magnitudes.

- **[CH13]** Verified: Jamshidian decomposition logic; Vasicek-Black bond-option formula (13.30)-(13.31); forward-bond volatility (13.27); total-variance factorisation (13.32); worked 1×3 option (13.7.1).

- **[CH14]** Verified: Heston bivariate SDE (14.14)-(14.15); Feller condition (14.9); Girsanov shifts (14.11)-(14.13); affine-preserving $\lambda^v$ choices preserve Heston form; Kolmogorov backward PDE (14.24); Riccati ODE derivation (14.28)-(14.31) — I rederived the coefficient matching in $v^0$ and $v^1$; closed-form $d, g_*, B, A$ (14.32)-(14.35); Gil-Pelaez inversion (14.41); Carr-Madan damping setup (14.44); expected variance formula $m_t = v_0 e^{-\kappa t} + \theta(1-e^{-\kappa t})$; fair VS strike (14.56); characteristic function shift by $-i$ for share measure. Only slip: numerical $d(i) \approx 2.036 + 0.405 i$ in §14.9 doesn't quite match my redo (I get $\approx 2.070 + 0.398 i$), but this is rounding; the structural derivation is correct.

- **[CH15]** Verified: caplet payoff (15.5)-(15.6); Vasicek-forward-bond martingale argument (15.7)-(15.10); Black-style caplet formula (15.11)-(15.12); Black-76 caplet (15.17)-(15.18); cap = sum of caplets decomposition (15.13); Bachelier alternative (15.4b); swaption derivation under annuity measure.

---

**Bottom line.** Three genuine math/technical errors, all local: CH03 covariance matrix (trivially fixable), CH08 phantom $-\delta$ drift in the forward SDE (requires rewriting one paragraph), and CH09 eq (9.6) extra VaR factor in Student-$t$ ES (delete one factor). Neither of the last two propagates to downstream derivations. The rest of the guide is mathematically solid.
