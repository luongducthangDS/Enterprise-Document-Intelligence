/**
 * HR Document Intelligence Agent - Enterprise SaaS Mock Data
 */

window.MOCK_DATA = {
  currentUser: {
    name: "Alex Rivera",
    email: "alex.rivera@company.com",
    role: "Employee", // "Employee" | "HR Admin"
    avatar: "AR",
    department: "Engineering"
  },

  adminUser: {
    name: "Linh Tran",
    email: "linh.tran@company.com",
    role: "HR Admin",
    avatar: "LT",
    title: "Lead HR Business Partner"
  },

  documents: [
    {
      id: "doc-1",
      name: "Hybrid_Working_Policy_2026.pdf",
      category: "Workplace Policy",
      version: "3.2",
      effectiveDate: "15 January 2026",
      owner: "HR Policy Team",
      fileType: "PDF",
      size: "2.4 MB",
      indexStatus: "Indexed",
      lastIndexed: "2 hours ago",
      status: "Active",
      chunks: 142,
      content: `Section 2.1: Hybrid Working Schedule & Eligibility
Eligible employees may work remotely up to 2 days per week upon manager approval. Team members must coordinate their schedule with their manager and attend mandatory on-site meetings. Core collaboration hours across all offices are 10:00 AM - 4:00 PM local time.`
    },
    {
      id: "doc-2",
      name: "Annual_Leave_and_PTO_Guidelines_2026.pdf",
      category: "Leave Policy",
      version: "4.0",
      effectiveDate: "01 January 2026",
      owner: "Benefits Team",
      fileType: "PDF",
      size: "1.8 MB",
      indexStatus: "Indexed",
      lastIndexed: "1 day ago",
      status: "Active",
      chunks: 98,
      content: `Section 1.3: Annual Paid Leave Entitlement
Full-time employees receive 18 days of paid annual leave per calendar year. Unused leave up to 5 days can carry over to Q1 of the subsequent year.`
    },
    {
      id: "doc-3",
      name: "Probation_Review_and_Onboarding_SOP.pdf",
      category: "Onboarding",
      version: "2.1",
      effectiveDate: "10 November 2025",
      owner: "Talent Ops",
      fileType: "PDF",
      size: "3.1 MB",
      indexStatus: "Indexed",
      lastIndexed: "3 days ago",
      status: "Active",
      chunks: 115,
      content: `Section 3.4: Probation Assessment Timeline
The standard probation period is 90 days. Formal 30-day, 60-day, and 90-day check-in reviews are conducted by the line manager.`
    },
    {
      id: "doc-4",
      name: "Payroll_and_Direct_Deposit_Guide.pdf",
      category: "Finance & Payroll",
      version: "1.5",
      effectiveDate: "01 August 2025",
      owner: "Finance Ops",
      fileType: "PDF",
      size: "1.2 MB",
      indexStatus: "Indexed",
      lastIndexed: "5 days ago",
      status: "Active",
      chunks: 64,
      content: `Section 4.2: Updating Bank Information
Employees must submit bank detail updates via the Self-Service Payroll portal at least 5 business days prior to the payroll cut-off date (20th of each month).`
    }
  ],

  tickets: [
    {
      id: "HR-2048",
      employee: "Alex Rivera (Engineering)",
      employeeEmail: "alex.rivera@company.com",
      question: "Does the company reimburse home solar panel installation?",
      category: "Benefits & reimbursement",
      confidence: 31,
      priority: "Normal",
      assignee: "Linh Tran",
      sla: "18h 42m",
      status: "New", // "New" | "In review" | "Waiting for info" | "Resolved"
      createdDate: "Today, 09:20",
      lastUpdated: "10 mins ago",
      expectedResponse: "Within 1 business day",
      reason: "No approved HR document contained sufficient supporting evidence (Low confidence score 31%).",
      response: "",
      responder: "",
      responseTimestamp: ""
    },
    {
      id: "HR-2045",
      employee: "Sarah Chen (Marketing)",
      employeeEmail: "sarah.chen@company.com",
      question: "Can I request an extension for my parental leave allocation?",
      category: "Leave Policy",
      confidence: 45,
      priority: "High",
      assignee: "Minh HR",
      sla: "04h 15m",
      status: "In review",
      createdDate: "Yesterday, 14:15",
      lastUpdated: "1 hour ago",
      expectedResponse: "Today, 17:00",
      reason: "Special exception policy evaluation required.",
      response: "",
      responder: "",
      responseTimestamp: ""
    },
    {
      id: "HR-2039",
      employee: "David Kim (Sales)",
      employeeEmail: "david.kim@company.com",
      question: "What is the tuition reimbursement limit for professional certifications?",
      category: "Learning & Dev",
      confidence: 88,
      priority: "Low",
      assignee: "Linh Tran",
      sla: "Resolved",
      status: "Resolved",
      createdDate: "03 Aug 2026",
      lastUpdated: "04 Aug 2026",
      expectedResponse: "Completed",
      reason: "Verified against L&D Guidelines 2026.",
      response: "The annual tuition reimbursement cap for approved job-related certifications is $2,500 per employee per calendar year.",
      responder: "Linh Tran (HR Specialist)",
      responseTimestamp: "04 Aug 2026, 11:30"
    }
  ],

  ragResponses: {
    "hybrid": {
      confidence: 94,
      status: "Verified answer",
      answer: "Eligible employees may work remotely **up to 2 days per week** upon manager approval. Team members must coordinate their schedule with their manager and attend mandatory on-site meetings. Core collaboration hours across all offices are **10:00 AM – 4:00 PM** local time.",
      responseTime: "1.2s",
      requestId: "REQ-94812",
      citations: [
        {
          docId: "doc-1",
          title: "[1] Hybrid Working Policy",
          section: "Section 2.1",
          page: "Page 4",
          version: "3.2",
          effectiveDate: "15 January 2026",
          excerpt: "Eligible employees may work remotely up to 2 days per week upon manager approval. Team members must coordinate their schedule with their manager and attend mandatory on-site meetings."
        }
      ]
    },

    "solar_low": {
      confidence: 31,
      status: "Unverified",
      heading: "I couldn't verify this confidently",
      explanation: "I searched all approved HR documents, but found no policy mentioning home solar panel installation reimbursements. To ensure you receive accurate information without fabrication, this question should be reviewed by an HR Specialist.",
      citations: []
    },

    "solar_reindexed": {
      confidence: 95,
      status: "Verified answer",
      answer: "Under our updated **Home Workplace & Green Energy Subsidy Policy 2026**, full-time employees working remotely are eligible for a **50% matching subsidy up to $1,500** towards home solar panel or energy storage installation.",
      responseTime: "0.9s",
      requestId: "REQ-99410",
      citations: [
        {
          docId: "doc-5",
          title: "[1] Home_Workplace_Solar_Reimbursement_Policy_2026.pdf",
          section: "Section 4.1",
          page: "Page 2",
          version: "1.0",
          effectiveDate: "05 August 2026",
          excerpt: "Full-time employees working remotely are eligible for a 50% matching subsidy up to $1,500 towards home solar panel or energy storage installation."
        }
      ]
    }
  }
};
