# Qoyod — Complete Features & Integrations Reference
**Source:** Live audit of qoyod.com — May 2026  
**Use for:** LP copy, solution sections, feature cards, trust signals  
**Rule:** Never invent capabilities. Only claim what's in this file.

---

## PRODUCT SUITE

| Product | Arabic name | Target audience |
|---|---|---|
| Core Accounting | برنامج قيود المحاسبي | SMBs, accountants, CFOs |
| POS (Retail) | نظام نقاط البيع | Physical retail stores |
| Flavours (F&B POS) | قيود فليفرز | Restaurants, cafés, F&B |
| Pro Services | خدمات قيود الاحترافية | Business owners who want done-for-you |

---

## CORE ACCOUNTING — Full Feature List

### 1. Sales & Invoicing
- Create, send, and track sales invoices electronically
- ZATCA Phase 1 & 2 compliant e-invoices (digital signature + QR)
- Proforma invoices, quotations, credit notes
- Partial payments support
- Customer management and history
- Sales representative tracking via additional fields
- Recurring invoices (monthly automation)
- Invoice attachments and document management
- Email invoices directly to customers

### 2. Purchases
- Supplier management
- Purchase invoices and purchase orders
- Convert purchase orders to invoices
- Document attachments (bank transfers, receipts)

### 3. Inventory Management
- Multi-branch inventory with location mapping
- Real-time stock tracking (auto-update on sale)
- Inter-branch stock transfers
- Inventory adjustments (increase, write-off, damage)
- Product bundles
- Stock counting / physical count
- Barcode support
- Inventory reporting by branch/location (mobile-accessible)

### 4. Payroll
- Employee tracking (hours, wages, incentives)
- Wage calculation
- Payroll reports
- GOSI compliance (via Jisr integration)

### 5. Fixed Assets
- Asset types: land, buildings, machinery, equipment, vehicles
- Automatic depreciation calculation
- Asset maintenance tracking
- Asset disposal
- Fixed asset reports

### 6. Reports & Analytics
- Real-time financial reports
- Profit & loss statement
- Balance sheet
- Cash flow statement
- Sales and purchase reports
- Inventory reports
- Custom report builder
- Company performance dashboard
- All reports reflect live data — no manual entry

### 7. Cost Centers
- Segment revenue and spending by: department, project, product, salesman
- Compare project profitability
- Track salesperson performance
- Commission tracking

### 8. Projects & Tasks
- Assign tasks to team members
- Set project timelines
- Monitor team performance
- Link projects to invoices and accounting data
- Track earnings per client and per project in real time

### 9. Budgeting
- Set financial budgets per period
- Compare actual performance vs plan
- Variance analysis

### 10. Accounting Dimensions
- Financial segmentation by departments / projects / products
- Multi-dimensional reporting

### 11. User Management & Permissions
- Role-based access control (read / create / delete / approve)
- Multiple users per account
- PIN-based switching (POS)
- Individual transaction tracking per employee
- Prevent cross-department data access

### 12. VAT & Tax
- VAT calculation and reporting
- Advanced tax calculator
- ZATCA-compliant VAT filing
- Tax return preparation (via Pro Services)

### 13. Multi-Branch / Multi-Location
- Manage multiple stores from one account
- Branch-level financial comparison
- Centralized reporting across all locations

### 14. Payment Management
- Full and partial invoice payments
- Receipt voucher creation (with custom dates)
- Multiple bank account configuration
- Deferred payments and installments
- Refund management (to original method or store credit)

### 15. Document Management
- Attach documents to any transaction (invoices, purchase orders, bonds)
- Digital storage and backup
- Supports: commercial registration, bank transfers, quotations, contracts

### 16. Commercial Guarantee System
- Customer satisfaction tracking
- Warranty/guarantee management

### 17. Accounting Dimensions / Segmentation
- Budgets by department or project
- Cost tracking per unit, product, or service

### 18. Mobile App
- iOS · Android · Huawei AppGallery
- Full accounting access on mobile
- Inventory management by smartphone
- Real-time reports

---

## POS (POINT OF SALE) — Full Feature List

### Sales
- Smart cart with barcode scanning (USB, Bluetooth, camera)
- Weight-based barcode support
- Per-product discounts and promotions
- Partial payment support
- ZATCA Phase 1 & 2 compliant invoice on every sale (auto digital signature + QR)
- Full and partial credit notes linked to original invoices

### Payments
- Cash, card, or split payment
- Hala wallet
- Payment terminal integration
- Deferred payment and installment support
- Refund to original method or store credit

### Offline Mode
- Full POS functionality without internet
- Local transaction storage
- Instant sync on reconnect

### Inventory
- Auto-update inventory on every sale
- Auto-adjust on returns
- Real-time stock visibility

### User Management
- PIN-based user switching
- Granular permission controls per action
- Individual transaction tracking per employee
- Multiple users per device

### Reporting
- Daily session reports
- Shift reconciliation
- Last 10 transactions log
- Multi-branch unified dashboard

### Hardware Support
| Device | Screen | Printer | Connectivity | Weight |
|---|---|---|---|---|
| SUNMI D2 mini | 10.1" touch | Built-in 58mm thermal | WiFi / 4G | 1.94kg |
| SUNMI V2s | Android 11 | Built-in 58mm thermal | 4G / WiFi / Bluetooth | 417g |
| Huawei / Android tablets | Any | External (Epson) | WiFi | — |
| Web browser | — | External | WiFi | — |

---

## FLAVOURS (F&B POS) — Full Feature List

### Order Management
- QR ordering — customers order from their table directly
- Kitchen Display System (KDS) — orders sent to kitchen instantly, no paper
- Single screen for all order types: dine-in, delivery, table orders
- Order tracking from placement to fulfilment

### Cost & Profitability
- Cost per dish (100% visibility)
- Dish profitability analysis before selling
- Stock waste tracking (25% average reduction)
- Material cost across all branches

### Operations
- Multi-branch management from one dashboard
- 3× faster branch performance comparison
- Employee hours and wage tracking
- Operating cost monitoring

### Compliance
- ZATCA Phase 1 & 2 compliant invoices
- Automatic QR and digital signature on every receipt

### Integration with Core Accounting
- All F&B sales sync to Qoyod accounting automatically
- Inventory auto-updated on every sale

---

## PRO SERVICES — Full List

| Service | Arabic | What it does |
|---|---|---|
| Bookkeeping / مسك الدفاتر | خدمة مسك الدفاتر | Qoyod team runs your books daily inside your account |
| Tax Filing | خدمة الإقرارات الضريبية | VAT return preparation and filing |
| Setup Service | خدمة التأسيس | Full account setup, chart of accounts, opening balances |
| Cleanup Service | خدمة ترتيب الحسابات | Fix historical accounting errors |
| Qoyod Tahseel | قيود تحصيل | Invoice collection management |
| Qoyod Lend | قيود للتمويل | Access to business funding |

---

## INTEGRATIONS — Full List

### Government & Compliance
| Integration | What it does |
|---|---|
| ZATCA (هيئة الزكاة والضريبة والجمارك) | Automatic invoice exchange, Phase 1 & 2, digital signature, QR code generation |

### E-Commerce Platforms
| Integration | What syncs | Notes |
|---|---|---|
| Salla (سلة) | Orders → invoices, inventory quantities, accounting records | Via FaiSync; read orders + wallet access |
| Zid (زد) | Financial entries, inventory sync, ZATCA compliance | Full accounting automation |
| WooCommerce | Sales data, invoices | (Confirmed on homepage) |
| Shopify | Sales data, invoices | (Confirmed on homepage) |

### Automation
| Integration | What it does |
|---|---|
| Zapier | Connect any app to Qoyod; automate repetitive tasks without coding |
| Open API | Full REST API for custom integrations; tech partner program |

### HR & Payroll
| Integration | What it does |
|---|---|
| Jisr (جسر) | HR management, payroll processing, GOSI compliance |

### Payments & Fintech
| Integration | What it does |
|---|---|
| Geidea (جيدية) | Payment terminal processing, cash flow management |
| Hala | Wallet payments via POS |
| Moyasar (ميسر) | Payment gateway — MADA, Visa, Mastercard, Apple Pay |
| HyperPay | Payment gateway — MADA, Visa, Mastercard, Tabby, Tamara |
| Tamara | Buy Now Pay Later (BNPL) — Saudi market leader |
| Tabby | Buy Now Pay Later (BNPL) |

### Messaging & Productivity
| Integration | What it does |
|---|---|
| WhatsApp | Send invoices/notifications via WhatsApp |
| Google Sheets | Export/sync financial data |

### F&B Specific
| Integration | What it does |
|---|---|
| Foodics | Data exchange, workflow integration for F&B businesses |

---

## KEY BENEFIT STATS (use verbatim in copy)

| Stat | Source page |
|---|---|
| 80% reduction in monthly reconciliation time | Retail sector page |
| 70% less time preparing monthly invoices | Technology sector page |
| 40% less time preparing quotes | Services sector page |
| 28% profit margin improvement after pricing review | Services sector page |
| 80% fewer invoicing delays | Services sector page |
| 25% reduction in stock waste | F&B sector page |
| 100% visibility on cost per dish | F&B sector page |
| 3× faster branch performance comparison | F&B sector page |
| 2× faster identifying unprofitable services | Services sector page |

---

---

## PRICING PLANS (live — always verify at qoyod.com/pricing/)

| Plan | AR name | Annual price | Users | Branches | Key additions |
|---|---|---|---|---|---|
| Basic | الأساسية | 1,200 ⃁/yr | 1 | 1 | Invoices, payments, debit notes, basic reports |
| Professional ★ | الاحترافية | 1,800 ⃁/yr | 3 | 3 | Phase 1 e-invoicing, purchases, quotations, inventory |
| Advanced | المتقدمة | 2,211 ⃁/yr (33% off 3,300) | 5 | 5 | Fixed assets, API integrations, multi-dim analytics, phone support |
| Enterprise | باقة الأعمال | Custom (contact sales) | Unlimited | Unlimited | Custom API, dedicated account manager, team training |

**Professional** is tagged "مرشّحة لشركتك" (recommended).  
**Annual vs monthly:** up to 20% savings. 3-year commitment: 33% savings.

### Add-ons (annual)
| Add-on | Price/yr | What it adds |
|---|---|---|
| Additional branch/warehouse | 480 ⃁ | Per branch |
| Additional user | 240 ⃁ | Per employee |
| Point of Sale | 600 ⃁ | POS registers + inventory integration |
| Payroll module | 120 ⃁ | مسيّرات الرواتب |

### Trial & Terms
- **14 days free** — no credit card required — cancel anytime
- Payment methods: **Tamara** (BNPL) · **SADAD**
- Servers: local Saudi Arabia — ISO 27001 encrypted — daily automatic backups
- ZATCA Phase 2 included from Professional plan upward

---

## E-INVOICING (ZATCA) — Full Feature List

**Page:** qoyod.com/الفاتورة-الالكترونية/  
**Certified:** Phase 1 & Phase 2 officially

### Features
1. **UBL/XML format** — ZATCA-approved format, one click from Qoyod
2. **Auto QR code** — added to every invoice automatically
3. **Tax + simplified invoices** — both types supported
4. **VAT 15%** — calculated and displayed on every invoice automatically
5. **Tax number + entity data** — auto-included on all invoices
6. **Real-time Fatoorah submission** — every invoice sent instantly to منصة فاتورة
7. **Cloud archiving** — all invoices saved automatically to cloud
8. **Multi-user permissions** — granular control per employee
9. **Compliance reports** — VAT, withholding tax, invoice flow reports ready

### Key Claims (use verbatim)
- "معتمد رسمياً ويُصدر فواتير إلكترونية متوافقة مع المرحلتين الأولى والثانية"
- "يربط مباشرة مع منصة فاتورة بصيغة UBL/XML مع رمز QR والتوقيع الرقمي والختم المشفّر"
- "أقل من ساعة في معظم الحالات" (setup time)
- غرامات عدم الامتثال: **تبدأ من 5,000 ريال للمخالفة الواحدة** (use as urgency — not fake)
- "بدون مطوّر تقني أو تكاملات خارجية"

### Target audience segments on this page
SMEs · Accountants & firms · F&B · Retail

---

## API & INTEGRATIONS — Technical Spec

**API version:** v2.0 (stable, production-tested)  
**No additional fees for API usage**  
**Auth:** Private API key per organization  
**Protocol:** HTTPS encrypted  
**Response format:** JSON  
**Filtering:** Ransack-supported  
**HTTP codes:** 200, 201, 400, 404, 500

### 19 API Resources
Accounts · Products · Inventories · Product Categories · Units · Vendors · Purchase Orders · Bills · Bill Payments · Customers · Quotes · Invoices · Invoice Payments · Credit Notes · Debit Notes · Receipts · Journal Entries · Simple Bills · (+ more via partner program)

### Confirmed Integration Partners (from api-integrations page)
| Partner | Category | What syncs |
|---|---|---|
| Salla (سلة) | E-commerce | Orders → invoices, inventory auto-sync |
| Zid (زد) | E-commerce | Financial entries, inventory, ZATCA |
| WooCommerce | E-commerce | Orders and invoices |
| Shopify | E-commerce | Orders and invoices |
| WhatsApp | Messaging | Invoice sending/notifications |
| Google Sheets | Productivity | Pull accounting data for custom reports |
| ZATCA | Compliance | Phase 1 & 2 invoice exchange |
| Zapier | Automation | Connect any app, automate workflows |

---

## PRO SERVICES — Full Detail

**Page:** qoyod.com/pro-services/  
**Pricing:** Quote-based — free diagnostic meeting, no commitment  
**Accountants:** SOCPA-certified (محاسبون معتمدون من SOCPA)  
**NDA:** Confidentiality agreement required  
**Contracts:** No long-term commitment, 30-day cancellation notice

### 4 Services

| Service | Arabic | Frequency | Includes |
|---|---|---|---|
| Bookkeeping | مسك الدفاتر | Monthly | Daily + monthly journal entries, bank reconciliation, income statement, balance sheet, AR/AP tracking |
| Tax Filing | الإقرارات الضريبية | Quarterly | VAT return prep + submission, invoice review before filing, ZATCA representation, weekly deadline reminders |
| Accounting Setup | التأسيس المحاسبي | One-time | Chart of accounts, VAT + e-invoice config, POS + integration setup, team training |
| Account Cleanup | ترتيب الحسابات | One-time | Historical audit, error correction, balance sheet reconstruction, audit-ready records |

### Target audience
- Busy business owners with no time for daily follow-up
- Growing companies wanting professional accounting without hiring
- Startups establishing correct financial foundations

### Trust signals on this page
- ⭐ 4.7/5 — 1,000+ Google reviews
- SOCPA-certified accountants
- ZATCA Phase 2 approved
- NDA / confidentiality agreement
- No long-term contracts

### CTA
"احصل على عرض سعر مجاني الآن" — lead form: name, phone, business type, business size, service needed

---

## COMPLIANCE CERTIFICATIONS (use as trust signals)

- ✓ متوافق مع زاتكا — المرحلة الثانية (ZATCA Phase 2 certified)
- ✓ توقيع رقمي + رمز QR على كل فاتورة
- ✓ متوافق مع اشتراطات حماية البيانات والخصوصية
- ✓ معتمد من هيئة الزكاة والضريبة والجمارك

---

## SECTOR COVERAGE (8 industries + general)

| Sector | AR | Key pain Qoyod solves |
|---|---|---|
| Retail | التجزئة | POS ↔ accounting disconnect, ZATCA |
| F&B / Restaurants | الأغذية والمشروبات | Kitchen-to-invoice, dish cost, multi-branch |
| Services | الخدمات | Project billing, client profitability |
| Technology | التقنية | Recurring invoices, project-based billing |
| Manufacturing | التصنيع والإنتاج | Production cost, inventory, asset tracking |
| Real Estate & Contracting | العقارات والمقاولات | Project accounting, asset management |
| Education | التعليم | Tuition invoicing, payroll |
| Rental | التأجير | Recurring invoices, asset tracking |
| Legal | المكاتب القانونية | Client billing, trust accounts |
| Operations & Maintenance | التشغيل والصيانة | Contract billing, team costs |
