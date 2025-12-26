# Southeast Asia Platform Expansion Plan
**MiroFish Multi-Platform Support Strategy**

---

## Executive Summary

**Goal:** Expand MiroFish to support all major social media platforms popular in Southeast Asia, enabling more accurate and inclusive public opinion analysis and AI-powered prediction for the region's diverse digital landscape.

**Current State:** 2 generic platforms (Twitter-like, Reddit-like)  
**Target State:** 8+ region-specific platforms with authentic behavior patterns  
**Approach:** Gradual, phased implementation with zero-downtime and backward compatibility

---

## 1. Business Rationale

### Why Southeast Asian Platforms Matter

#### Market Reality
- **1.3 billion users** across Southeast Asia (ASEAN region)
- **Facebook dominates**: 70%+ market share in most SE Asian countries
- **LINE**: 180M+ users (Thailand, Taiwan, Indonesia)
- **Zalo**: 75M+ users (Vietnam's #1 platform)
- **WeChat**: Major in Chinese-speaking communities across SEA
- **Telegram**: Growing rapidly for communities and news

#### Current Limitation
MiroFish uses **generic Western patterns** (Twitter/Reddit):
- ❌ Doesn't reflect actual SE Asian social media behavior
- ❌ Missing platform-specific featuAIzaSyC-yD_IXlRUPZMyeW92VyJpBh0nOwyqK-MAIzaSyC-yD_IXlRUPZMyeW92VyJpBh0nOwyqK-Mres (stickers, mini-apps, payment integration)
- ❌ Can't simulate cross-platform dynamics (users active on multiple platforms)
- ❌ Limited cultural context (language mixing, emoji usage, sharing patterns)

#### Business Impact
**With SE Asian Platform Support:**
- ✅ **More accurate predictions** for regional markets
- ✅ **Better client value** for brands, governments, NGOs in SEA
- ✅ **Competitive advantage** over Western-focused tools
- ✅ **Market expansion** into high-growth region

---

## 2. Southeast Asian Platform Landscape

### Priority Platforms (Ordered by Impact)

| Platform | Users | Primary Markets | Use Cases | Priority |
|----------|-------|----------------|-----------|----------|
| **Facebook** | 400M+ SEA | All countries | Public discourse, news, groups | **P0** |
| **LINE** | 180M+ | Thailand, Taiwan | Messaging, stickers, communities | **P0** |
| **Zalo** | 75M+ | Vietnam | Messaging, news, social networking | **P1** |
| **Telegram** | 70M+ SEA | All countries | News channels, communities, bots | **P1** |
| **Instagram** | 150M+ SEA | Urban demographics | Visual content, influencers | **P1** |
| **TikTok** | 325M+ SEA | Youth (16-34) | Short video, trends, viral content | **P2** |
| **WeChat** | 50M+ SEA | Chinese communities | Super-app (messaging, payment, services) | **P2** |
| **Viber** | 30M+ | Philippines, Myanmar | Messaging, stickers | **P3** |

### Platform Characteristics

#### Facebook (P0 - Highest Priority)
**Why it matters:**
- Dominant platform across ALL SE Asian countries
- Primary source of news and public discourse
- Active community groups (private & public)
- Marketplace integration (commerce)
- Events and local organizing

**Unique Features:**
- **Groups** (closed communities, discussion forums)
- **Pages** (brands, public figures, news outlets)
- **Reactions** (Like, Love, Haha, Wow, Sad, Angry)
- **Sharing culture** (extremely high share rates in SEA)
- **Comment threads** (deep, nested conversations)

**Simulation Value:**
- Understand viral sharing dynamics
- Model group polarization
- Predict misinformation spread
- Analyze brand sentiment

---

#### LINE (P0 - Highest Priority)
**Why it matters:**
- **#1 in Thailand** (90%+ smartphone users)
- Strong in Taiwan, Indonesia
- Not just messaging - full social ecosystem
- Major platform for business and government communication

**Unique Features:**
- **Stickers** (core communication method, emotional expression)
- **Official Accounts** (businesses, celebrities, news)
- **Timeline** (social feed like Twitter)
- **Groups & Chats** (private communication)
- **Rich messages** (images, carousels, interactive content)

**Simulation Value:**
- Model sticker-based emotional expression
- B2C communication patterns
- Youth engagement behaviors
- Cross-platform coordination (LINE + Facebook common)

---

#### Zalo (P1 - High Priority)
**Why it matters:**
- **Vietnam's dominant platform** (75M users in 100M population)
- Government-preferred platform
- Local alternative to WhatsApp/WeChat
- Strong news and content ecosystem

**Unique Features:**
- **Zalo News** (curated news feed)
- **Communities** (interest-based groups)
- **Official Accounts** (verified businesses/organizations)
- **Mini-apps** (in-app services)
- **Vietnamese-optimized** (excellent Vietnamese text processing)

**Simulation Value:**
- Vietnam-specific public opinion
- Government communication effectiveness
- Local vs global platform dynamics
- Regional app ecosystem behavior

---

#### Telegram (P1 - High Priority)
**Why it matters:**
- Fastest-growing platform in SEA
- Primary channel for **news and activism**
- Strong in communities that value privacy/encryption
- Popular for crypto, tech, political organizing

**Unique Features:**
- **Channels** (broadcast to unlimited subscribers)
- **Public Groups** (up to 200k members)
- **Bots** (automation, information delivery)
- **Poll/Quiz features** (engagement tools)
- **Forwarding culture** (chain messages common in SEA)

**Simulation Value:**
- Information cascade dynamics
- Activist organizing patterns
- Bot-human interaction
- Cross-group coordination

---

## 3. Technical Architecture Strategy

### Core Design Principles

#### 1. Platform Abstraction
**Current Problem:**
Code is tightly coupled to Twitter/Reddit patterns

**Solution:**
Create **Platform Behavior Profiles** - abstract behavior templates that can be configured per platform without changing core simulation engine.

**Benefits:**
- ✅ Add new platforms without touching core code
- ✅ Easy to maintain and test
- ✅ Mix and match behaviors (e.g., "Facebook = Reddit groups + Twitter feed + Reactions")

---

#### 2. Modular Action System
**Current Problem:**
Actions are hardcoded (CREATE_POST, LIKE_POST, etc.)

**Solution:**
**Extensible Action Registry** - platforms can register custom actions (SEND_STICKER, FORWARD_MESSAGE, CREATE_POLL)

**Benefits:**
- ✅ Platform-specific features without breaking existing platforms
- ✅ Easy to add culturally-specific actions
- ✅ Clear separation of concerns

---

#### 3. Multi-Platform Agents
**Current Problem:**
Agents exist on one platform at a time

**Solution:**
**Cross-Platform Agent Profiles** - agents can be active on multiple platforms simultaneously with different personas/behaviors per platform

**Real-World Pattern:**
- Users behave differently on Facebook (real name) vs Telegram (pseudonymous)
- Content shared on Instagram → discussed on LINE groups
- News from Telegram channels → debated in Facebook groups

**Benefits:**
- ✅ Model realistic cross-platform influence
- ✅ Track information flow between platforms
- ✅ Understand platform-switching behavior

---

### Implementation Approach: Platform Behavior Profiles

Instead of coding each platform separately, define **JSON/YAML configuration profiles**:

```yaml
# Example: Facebook Platform Profile
name: "Facebook"
type: "social_network"
features:
  - groups
  - pages
  - timeline
  - marketplace
actions:
  post:
    - CREATE_POST (public, group, page)
    - SHARE_POST (with comment)
    - CREATE_EVENT
  engagement:
    - REACT (like, love, haha, wow, sad, angry)
    - COMMENT (nested threads, tag users)
    - SHARE
  social:
    - FRIEND_REQUEST
    - JOIN_GROUP
    - FOLLOW_PAGE
    - BLOCK_USER
content_types:
  - text
  - image
  - video
  - link_preview
  - poll
algorithms:
  feed: "engagement_ranked" # vs chronological
  virality: "high_share_multiplier"
  group_dynamics: "echo_chamber"
cultural_params:
  emoji_usage: "very_high"
  sharing_rate: "3x_global_average"
  comment_threads: "deep_nested"
```

**Why This Works:**
1. **No code changes** to add new platform - just new config file
2. **Easy for non-developers** to tune platform behavior
3. **Version controlled** - can track platform evolution
4. **A/B testing** - try different algorithm profiles
5. **Gradual rollout** - start with subset of features, expand over time

---

## 4. Phased Implementation Roadmap

### Phase 0: Foundation (Weeks 1-2)
**Goal:** Prepare architecture without breaking existing functionality

**Tasks:**
1. **Refactor Platform Abstraction Layer**
   - Extract Twitter/Reddit logic into platform profiles
   - Create Platform Behavior Config schema
   - Migrate existing platforms to new system
   - **Risk Mitigation:** Run parallel systems, validate identical output

2. **Extend Action System**
   - Make action types configurable (not hardcoded enum)
   - Add action metadata (platform, visibility, content type)
   - Update database schema to support flexible actions
   - **Risk Mitigation:** Backward-compatible schema migration

3. **Multi-Platform Agent Support**
   - Allow agents to have multiple platform profiles
   - Track cross-platform activity
   - **Risk Mitigation:** Start with single-platform agents, add multi-platform flag

**Deliverables:**
- ✅ Refactored codebase (no functionality change - pure refactor)
- ✅ 100% test coverage maintained
- ✅ Documentation for platform config format

---

### Phase 1: Facebook Integration (Weeks 3-5)
**Goal:** Add Facebook as first SE Asian platform

**Why Facebook First:**
- Highest impact (used across all SE Asian countries)
- Best documented behavior patterns
- Most client demand

**Tasks:**
1. **Create Facebook Platform Profile**
   - Define all Facebook-specific actions
   - Configure feed algorithm parameters
   - Set cultural behavior defaults

2. **Implement Facebook-Specific Features**
   - Reactions (6 types vs binary like)
   - Groups (public/private/closed)
   - Pages (business/community)
   - Nested comment threads
   - Share with commentary

3. **Agent Behavior Modeling**
   - Facebook-specific posting patterns
   - Group membership dynamics
   - Sharing cascades
   - Reaction patterns (cultural differences)

4. **Testing & Validation**
   - Compare with real Facebook data patterns
   - Validate viral spread mechanics
   - Test group polarization

**Deliverables:**
- ✅ Facebook platform fully functional
- ✅ Side-by-side comparison: Twitter vs Facebook behavior
- ✅ Documentation: "How to run Facebook-only simulation"

**Risk Mitigation:**
- Feature flags: Disable Facebook if issues arise
- Parallel testing: Run existing platforms alongside Facebook
- Gradual rollout: Internal testing → beta users → production

---

### Phase 2: LINE Integration (Weeks 6-8)
**Goal:** Add LINE for Thailand/Taiwan markets

**Why LINE Second:**
- Second-highest priority market
- Different paradigm (messaging-first vs feed-first)
- Tests system flexibility

**Tasks:**
1. **Create LINE Platform Profile**
   - Sticker system (structured emotional expression)
   - Official Accounts (1-to-many communication)
   - Timeline (social feed)
   - Group chats (private conversations)

2. **Sticker Emotion System**
   - Map stickers to emotional states
   - Model sticker-based communication patterns
   - Cultural sticker preferences

3. **Official Account Behavior**
   - Brand-to-consumer communication
   - Push messaging (vs pull/feed)
   - Rich message templates

4. **Testing & Validation**
   - Compare Thai user behavior patterns
   - Validate sticker substitution for text
   - Test official account engagement

**Deliverables:**
- ✅ LINE platform operational
- ✅ Sticker emotion library
- ✅ Thailand-specific simulation templates

---

### Phase 3: Zalo & Telegram (Weeks 9-11)
**Goal:** Add Vietnam-specific (Zalo) and privacy-focused (Telegram) platforms

**Tasks:**
1. **Zalo Platform Profile**
   - Vietnamese language optimization
   - Zalo News integration
   - Communities and mini-apps
   - Government communication patterns

2. **Telegram Platform Profile**
   - Channels (broadcast)
   - Groups (discussion)
   - Bots (automation)
   - Forwarding chains
   - Poll/quiz features

3. **Cross-Platform Dynamics**
   - Information flow: Telegram → Facebook
   - Activist coordination: Telegram planning → Facebook execution
   - News spread: Telegram channels → LINE groups

**Deliverables:**
- ✅ Zalo operational (Vietnam market ready)
- ✅ Telegram operational (activist/news scenarios)
- ✅ Cross-platform simulation capability

---

### Phase 4: Instagram & TikTok (Weeks 12-15)
**Goal:** Add visual/video platforms for youth demographics

**Tasks:**
1. **Instagram Profile**
   - Image-first content
   - Stories (ephemeral content)
   - Influencer dynamics
   - Hashtag discovery
   - Visual aesthetics scoring

2. **TikTok Profile**
   - Short video format
   - Algorithm-driven discovery (FYP)
   - Trend propagation
   - Sound/music virality
   - Challenge participation

3. **Content Type Expansion**
   - Image analysis (not just text)
   - Video metadata (duration, music, effects)
   - Visual trend detection

**Deliverables:**
- ✅ Instagram + TikTok platforms
- ✅ Visual content simulation
- ✅ Influencer behavior modeling

---

### Phase 5: WeChat & Viber (Weeks 16-18)
**Goal:** Complete platform coverage for niche communities

**Tasks:**
1. **WeChat Profile**
   - Super-app ecosystem
   - Mini-programs
   - WeChat Pay integration
   - Moments (social feed)
   - Official Account ecosystem

2. **Viber Profile**
   - Philippines/Myanmar focus
   - Communities
   - Sticker marketplace
   - Public chats

**Deliverables:**
- ✅ All 8 platforms operational
- ✅ Full SE Asian market coverage

---

## 5. Risk Mitigation Strategy

### Technical Risks

#### Risk 1: Breaking Existing Functionality
**Impact:** High - Could break production simulations

**Mitigation:**
1. **Comprehensive test suite** - 100% coverage maintained
2. **Parallel systems** - Run old + new side-by-side, validate identical output
3. **Feature flags** - Disable new platforms if issues detected
4. **Gradual rollout** - Internal → Beta → Production
5. **Rollback plan** - Can revert to previous version within 5 minutes

---

#### Risk 2: Performance Degradation
**Impact:** Medium - More platforms = more computation

**Mitigation:**
1. **Lazy loading** - Only load active platforms
2. **Caching layer** - Platform configs cached in memory
3. **Horizontal scaling** - Can add more simulation workers
4. **Monitoring** - Track performance metrics per platform
5. **Optimization pass** - Profile and optimize before each phase

---

#### Risk 3: Data Schema Changes
**Impact:** High - Breaking database migrations

**Mitigation:**
1. **Backward-compatible migrations** - Old data still readable
2. **Schema versioning** - Track migration history
3. **Migration testing** - Test on copy of production data
4. **Incremental changes** - Small migrations, not big-bang
5. **Data validation** - Verify data integrity after migration

---

### Business Risks

#### Risk 1: Scope Creep
**Impact:** High - Could delay delivery indefinitely

**Mitigation:**
1. **Phased approach** - Deliver value incrementally
2. **MVP first** - Core features before nice-to-haves
3. **Feature prioritization** - P0/P1/P2 system
4. **Regular reviews** - Weekly assessment of scope vs timeline
5. **Clear acceptance criteria** - Define "done" upfront

---

#### Risk 2: Insufficient Testing
**Impact:** High - Bugs in production

**Mitigation:**
1. **Test-driven development** - Write tests first
2. **Real-world validation** - Compare with actual platform data
3. **Beta testing** - Recruit SE Asian users for feedback
4. **Cultural review** - Local experts validate behavior realism
5. **Automated regression** - CI/CD runs full test suite

---

#### Risk 3: Maintenance Burden
**Impact:** Medium - Too many platforms to maintain

**Mitigation:**
1. **Platform config system** - Centralized, not scattered code
2. **Documentation** - Each platform has clear docs
3. **Automated tests** - Detect breakage immediately
4. **Version tracking** - Know when platforms change
5. **Community contributions** - Open config format for community input

---

## 6. Success Metrics

### Technical Metrics
- ✅ **Zero downtime** during platform additions
- ✅ **<5% performance degradation** with all 8 platforms
- ✅ **100% test coverage** maintained
- ✅ **<3% bug escape rate** to production
- ✅ **Platform parity** - All platforms support core action set

### Business Metrics
- ✅ **Client adoption** - 50%+ of SE Asian clients use new platforms
- ✅ **Prediction accuracy** - Improved accuracy for SE Asian markets
- ✅ **Market expansion** - Can bid on SE Asia-specific projects
- ✅ **User satisfaction** - 4.5/5+ rating for new platforms
- ✅ **Revenue impact** - Measurable increase in SE Asian sales

### Cultural Metrics
- ✅ **Behavioral realism** - SE Asian users confirm "this matches reality"
- ✅ **Language support** - Native speakers validate accuracy
- ✅ **Regional relevance** - Captures local nuances (stickers, sharing, etc.)
- ✅ **Cross-platform accuracy** - Matches real cross-platform behavior

---

## 7. Team Requirements

### Roles Needed

#### 1. Backend Engineer (Lead)
- Refactor platform abstraction layer
- Implement platform config system
- Database schema migrations
- **Time:** 40% allocation for 18 weeks

#### 2. ML/Behavior Modeling Specialist
- Research SE Asian social media behavior patterns
- Design platform-specific algorithms
- Validate against real-world data
- **Time:** 30% allocation for 18 weeks

#### 3. QA Engineer
- Write comprehensive test suites
- Run regression testing
- Validate platform behavior realism
- **Time:** 25% allocation for 18 weeks

#### 4. Cultural/Regional Consultants
- Thailand expert (LINE behavior)
- Vietnam expert (Zalo behavior)
- Facebook SEA expert (regional differences)
- **Time:** 10 hours per platform (consulting, not full-time)

#### 5. Product Manager
- Prioritize features
- Manage scope
- Coordinate with clients/stakeholders
- **Time:** 20% allocation for 18 weeks

---

## 8. Alternative Approaches (Considered & Rejected)

### Alternative 1: Third-Party Platform APIs
**Idea:** Use actual Facebook/LINE/Zalo APIs instead of simulation

**Rejected Because:**
- ❌ **Privacy/legal issues** - Can't simulate real user accounts
- ❌ **API limitations** - Rate limits, restricted access
- ❌ **Cost** - API access fees prohibitive at scale
- ❌ **Control** - Can't manipulate time, can't rewind, can't inject scenarios
- ❌ **Ethics** - Shouldn't manipulate real social networks

**Correct Approach:** Simulate authentic behavior patterns, not use real platforms

---

### Alternative 2: Generic "Asian Platform" Template
**Idea:** Create one "Asian social media" platform instead of 8 specific ones

**Rejected Because:**
- ❌ **Inaccurate** - LINE ≠ Zalo ≠ Facebook in SEA
- ❌ **Low value** - Clients need platform-specific insights
- ❌ **Misses nuances** - Thai Facebook ≠ US Facebook
- ❌ **Not competitive** - Need specificity to differentiate

**Correct Approach:** Platform-specific configs that capture real differences

---

### Alternative 3: AI-Generated Platform Behavior
**Idea:** Use LLM to auto-generate platform behaviors

**Rejected Because:**
- ❌ **Unpredictable** - LLM hallucinations could introduce bugs
- ❌ **Not validated** - Need human expertise to verify correctness
- ❌ **Maintenance** - Hard to debug AI-generated behavior
- ❌ **Performance** - Real-time LLM calls too slow for simulation

**Use LLMs For:** Research assistance, not runtime behavior

---

## 9. Open Questions for Team Discussion

### Technical
1. **Database strategy:** PostgreSQL vs MongoDB for flexible platform schemas?
2. **Config format:** YAML vs JSON vs custom DSL for platform profiles?
3. **Performance target:** What's acceptable simulation speed with 8 platforms?
4. **Multi-platform agents:** How to handle agent personality consistency across platforms?

### Business
1. **Revenue model:** Premium feature, or included in base product?
2. **Market focus:** Which SE Asian countries to prioritize for sales?
3. **Partnership needs:** Should we partner with local firms for cultural expertise?
4. **Client readiness:** Do current clients have SE Asian use cases now?

### Product
1. **UI changes:** How to present 8 platforms in UI without overwhelming users?
2. **Documentation:** What level of platform docs needed for clients?
3. **Training:** Do we need cultural training for support team?
4. **Validation:** How to prove to clients that behavior is realistic?

---

## 10. Recommendation

### Proceed with Phased Approach ✅

**Rationale:**
1. **Clear ROI** - SE Asian market is high-growth, underserved
2. **Technical feasibility** - Platform abstraction is clean architecture
3. **Risk-managed** - Gradual rollout minimizes disruption
4. **Competitive advantage** - Few competitors have SE Asia depth
5. **Client demand** - Already have requests for these platforms

### Next Steps
1. **Team buy-in** - Discuss this plan, get consensus
2. **Resource allocation** - Confirm team availability
3. **Phase 0 start** - Begin architecture refactoring (2 weeks)
4. **Client pre-sales** - Gauge interest, potential revenue
5. **Recruit consultants** - Find SE Asian cultural experts

### Timeline
- **Phase 0 (Foundation):** Weeks 1-2
- **Phase 1 (Facebook):** Weeks 3-5  
- **Phase 2 (LINE):** Weeks 6-8
- **Phase 3 (Zalo + Telegram):** Weeks 9-11
- **Phase 4 (Instagram + TikTok):** Weeks 12-15
- **Phase 5 (WeChat + Viber):** Weeks 16-18

**Total: 18 weeks (4.5 months) to full SE Asian platform coverage**

---

## Appendix A: Platform Feature Comparison Matrix

| Feature | Facebook | LINE | Zalo | Telegram | Instagram | TikTok | WeChat | Viber |
|---------|----------|------|------|----------|-----------|--------|--------|-------|
| Feed/Timeline | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ (FYP) | ✅ (Moments) | ❌ |
| Groups/Communities | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| Direct Messaging | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Stickers | Basic | ★★★★★ | ★★★★ | ★★★ | ❌ | ❌ | ★★★★ | ★★★★ |
| Stories/Ephemeral | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Video (Short) | ✅ (Reels) | ❌ | ❌ | ❌ | ✅ (Reels) | ✅ | ❌ | ❌ |
| Live Streaming | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| E-commerce | ✅ (Marketplace) | ✅ (Shopping) | ❌ | ❌ | ✅ (Shop) | ✅ (Shop) | ✅ (Pay) | ❌ |
| Official Accounts | ✅ (Pages) | ✅ (OA) | ✅ (OA) | ✅ (Channels) | ✅ (Business) | ✅ (Creator) | ✅ (OA) | ✅ (Bots) |
| Polls | ✅ | ❌ | ❌ | ✅ | ✅ (Stories) | ❌ | ❌ | ❌ |
| Reactions (Multi) | ✅ (6 types) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Legend:**
- ★★★★★ = Core platform feature
- ✅ = Supported
- ❌ = Not available
- (Term) = Platform-specific name

---

## Appendix B: Cultural Behavior Patterns by Platform

### Facebook in Southeast Asia
- **Sharing culture:** 3-5x higher share rate than Western markets
- **Group dynamics:** Very active closed groups (family, alumni, local community)
- **Political engagement:** Major platform for news, activism, political debate
- **Comment threads:** Long, nested discussions (10+ levels deep common)
- **Emoji usage:** Heavy emoji use, especially in comments
- **Business use:** SMEs rely on Facebook for customer service

### LINE in Thailand
- **Sticker dependency:** Stickers replace text in 40%+ of messages
- **Official Accounts:** Follow brands, celebrities, government accounts
- **Group chats:** Family groups extremely active, multi-generational
- **Timeline use:** Less active than messaging, but exists
- **Business:** Restaurants, shops use LINE for orders/delivery

### Zalo in Vietnam
- **Government-preferred:** Official communication via Zalo
- **News consumption:** Zalo News is primary news source
- **Communities:** Interest-based communities very active
- **Privacy:** Local platform = trusted more than foreign platforms
- **Language:** Excellent Vietnamese language support (tone marks, etc.)

### Telegram in Southeast Asia
- **News channels:** Primary source for breaking news
- **Activism:** Used for organizing, especially sensitive topics
- **Crypto community:** Strong crypto/tech community presence
- **Forwarding chains:** Viral messages spread through forwarding
- **Privacy-conscious:** Growing among users concerned about surveillance

---

**End of Plan**

This document is a living plan - revise as we learn more!
