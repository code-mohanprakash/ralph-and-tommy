# Who this is for, and what we assume

Written before the code. The brief says to start from the people, not the technology, and to
write down assumptions about how Fleek's buyers and sellers behave. Each assumption below says what
the design does because of it, and what changes if it turns out to be wrong.

## The people

### Buyers

Online resellers (Vinted, Depop, eBay, Whatnot), vintage shops, and larger enterprise buyers,
buying 100 pieces at a time.

- **What they want from an agent:** stock that will sell, at a delivered cost per piece that
  leaves them a margin, without days of back-and-forth.
- **What they fear:** the agent spending more than they would. The seller learning their maximum.
  The wrong grade arriving. Losing a one-of-a-kind lot to a faster buyer.
- **What would make them trust it:** a limit the agent cannot break, approving their first few
  deals themselves, and a plain "why this deal".

### Sellers

Secondhand clothing suppliers and wholesalers selling in bulk, many of them in Pakistan and India.

- **What they want from an agent:** ageing stock sold, at or above their floor, to buyers who pay.
- **What they fear:** lowballers wasting their time. Their floor leaking: once buyers know it, every
  deal ends at it.
- **What would make them trust it:** the floor is never revealed and never broken, and an accepted
  offer is a real sale.

### Fleek's account managers

They keep buyers active today over WhatsApp, email, calls and stock lists.

- **What they want:** less time relaying messages, more time on big accounts and on deals that
  nearly closed.
- **What they need from the system:** a queue of deals waiting for a person, a way to step in, and
  a short list of near misses worth a call.

## Fleek facts we build on

From Fleek's public website and help centre, read on 28 Oct 2026. They may have changed since.

| Fact | What the design does with it |
|---|---|
| **Make an Offer:** the buyer bids; the seller accepts, counters or declines within 48 hours, or the offer expires. | The agents use the same moves and the same 48-hour clock, not a new protocol. |
| **Only the base price is negotiable.** Shipping is fixed and already included in the listed price. | Agents negotiate the base price. The buyer's limit is checked against the full delivered cost. |
| **Two main listing types:** Exact (the lot you see is the lot you get, one of one) and Representative (a pool of stock with 2–4 quantity tiers). | An Exact lot can only be sold once: the first accepted offer wins, the lot is locked, and other buyers are told it's sold. |
| **Grades** are A, B and C. | Grade is a hard filter in matching, before any price talk. |
| **Fees:** 15% commission on the seller's base price. Buyers pay a 2% protection fee, capped at £20. | Both sides' limits are checked after fees (see assumption 11). |
| **Strict anti-disintermediation policy:** sharing contact details can lead to a ban. | Agents exchange a fixed offer form, never free text, so contact details can't be passed. |

Sources: Fleek help centre articles on
[Make an Offer](https://support.joinfleek.com/hc/en-us/articles/42547229080475),
[listing types and grades](https://support.joinfleek.com/hc/en-us/articles/42547096235803),
[seller fees](https://support.joinfleek.com/hc/en-us/articles/42546479618331),
[buyer protection fee](https://support.joinfleek.com/hc/en-us/articles/43308599609243),
[off-platform trading](https://support.joinfleek.com/hc/en-us/articles/42540435572763).

## Our assumptions

Expect these to be challenged. None of them has been checked with Fleek's real data.

| # | We assume | So the design... | If it's wrong |
|---|---|---|---|
| 1 | Buyers think in **delivered cost per piece**, not lot price. | shows Ralph and the buyer cost per piece, including shipping and fees. | Show lot totals instead. Nothing in the limit checks changes. |
| 2 | Many buyers **don't know their maximum** exactly. They know their resale price and the margin they need. | takes a maximum, but the note to the buyer can work it out from resale price and margin. | Buyers type a maximum directly. No change. |
| 3 | Popular one-of-a-kind lots attract **several buyers at once**. | lets several buyers negotiate for the same lot. The first accepted offer wins, and the lot is locked so it can't be sold twice. | If contests are rare, the lock costs nothing. If almost every lot is contested, use a sealed-bid auction instead. |
| 4 | Small resellers **run out of budget** before they run out of interest. | keeps a budget across all of a buyer's live deals, so parallel deals can't overspend it together. | The budget check stays as a safety net. |
| 5 | Sellers take **a little less from fast, sure buyers**, and floors fall as stock ages. | lets Tommy trade price for quantity or speed, with a reason on every counter-offer. | Tommy concedes less. The floor check doesn't change. |
| 6 | **Quality mismatch, not price,** causes most disputes. | filters on grade first, and lets Ralph weigh a seller's quality score. | Weigh quality less. Matching still works. |
| 7 | Bulk discounts are **a few tiers, 0–15%**. | stores discounts as rules that code applies, not something the AI works out. | Change the rule table (per kilo, custom tiers). The agents don't change. |
| 8 | Buyers allow automatic deals **only after approving a few themselves**. | sends a buyer's first 3 deals, and any deal over £1,500, to the buyer for approval. | The thresholds are settings. |
| 9 | **Account managers' time** is today's bottleneck. | gives them a short call list of near misses, ranked, and a queue of deals waiting for approval. | The list is cheap to make, so it stays useful. |
| 10 | Fleek earns **a fixed commission** and never profits from the gap between the buyer's maximum and the seller's floor. | never uses that gap. The gain from each deal is split between buyer and seller and reported. | If Fleek took a spread, both sides would need to be told, or trust breaks. |
| 11 | A seller's floor means what they **receive after Fleek's 15% commission**. | accepts only if base price × 0.85 is at or above the floor. | If the floor means the listed price, the check drops the 0.85. One line. |

## Scaled down for the build

The brief describes about 50,000 buyers and 1,000 sellers. The build uses a seeded fake market of
**500 buyers, 50 sellers and about 1,500 lots**, the same every run. Prices are in pounds, stored as
whole pence. It's designed for the full size and tested at the small one; `docs/` will say what
changes at full scale.

## If a fact changes

The brief says Fleek may share a fact during the interview and ask how the design changes.

| If we learn that... | The design changes like this |
|---|---|
| Most lots are contested by several buyers | Tommy chooses between buyers, or a sealed-bid auction: the highest bid wins and pays the second-highest price. |
| Lots are priced per kilo | Change the unit in the settings. Shipping by weight makes the delivered cost more accurate. |
| Buyers mostly rebuy from the same sellers | Standing orders and relationship pricing. The new risk is deals moving off the platform. |
| Sellers won't state a floor | Estimate it from the offers they've accepted and declined before, with a person checking. |
| Shipping becomes negotiable (air vs sea) | One more field on the offer form. |
| Enterprise buyers want video handpicks | Ralph books the call instead of closing the deal. |
