/**
 * Every staff screen, declared as data (ADR-004). A list page, a create/edit
 * form, filters and workflow buttons come from one entry here; the generic
 * pages in app/(staff)/[module]/[resource] render them.
 *
 * `perm` is the backend permission resource (apps/org/rbac.py naming): the UI
 * shows a screen when the user can `<perm>.view`, the create/edit buttons with
 * `<perm>.manage`, and each action with its own `perm`.
 */
export type T = { en: string; hi: string };

export type FieldType =
  | "text" | "textarea" | "number" | "money" | "date" | "email" | "password"
  | "select" | "multiselect" | "relation" | "boolean";

export interface Option {
  value: string;
  label: T;
}

export interface FieldDef {
  name: string;
  label: T;
  type: FieldType;
  required?: boolean;
  options?: Option[];
  relation?: { resource: string; label: string; search?: boolean };
  createOnly?: boolean;
  editOnly?: boolean;
  help?: T;
}

export type ColumnType = "text" | "number" | "money" | "date" | "datetime" | "bool" | "tag";

export interface ColumnDef {
  key: string; // dot path into the row, e.g. "primary_guardian.phone"
  label: T;
  type?: ColumnType;
  sorter?: boolean;
  options?: Option[]; // for tag columns: value → label
}

export interface ActionDef {
  key: string;
  label: T;
  perm: string;
  method: "post" | "patch";
  path: string; // relative to the resource item, e.g. "return" → <resource>/<id>/return/
  body?: Record<string, unknown>;
  confirm?: T;
  danger?: boolean;
  visibleWhen?: { field: string; equals: unknown };
}

export interface FilterDef {
  field: string;
  label: T;
  options?: Option[];
  relation?: { resource: string; label: string };
}

export interface ResourceDef {
  name: string; // "<module>/<resource>" — also the API path under /api/
  module: string;
  label: T;
  perm: string;
  columns: ColumnDef[];
  fields?: FieldDef[];
  createEndpoint?: string; // POST target when it differs from the list URL
  canCreate?: boolean;
  canEdit?: boolean;
  canDelete?: boolean;
  deleteLabel?: T;
  actions?: ActionDef[];
  filters?: FilterDef[];
  importable?: boolean;
  searchable?: boolean;
  defaultSort?: { field: string; order: "asc" | "desc" };
}

export interface ModuleDef {
  key: string;
  label: T;
  icon: string; // @ant-design/icons component name
}

const t = (en: string, hi: string): T => ({ en, hi });
const opt = (value: string, en: string, hi: string): Option => ({ value, label: t(en, hi) });

const GENDER = [opt("male", "Male", "पुरुष"), opt("female", "Female", "महिला"), opt("other", "Other", "अन्य")];
const STUDENT_STATUS = [opt("active", "Active", "सक्रिय"), opt("passed_out", "Passed out", "उत्तीर्ण"), opt("left", "Left", "छोड़ दिया")];
const STAFF_STATUS = [opt("active", "Active", "सक्रिय"), opt("left", "Left", "छोड़ दिया")];
const EMPLOYMENT = [opt("permanent", "Permanent", "स्थायी"), opt("contract", "Contract", "अनुबंध"), opt("part_time", "Part-time", "अंशकालिक")];
const PROGRAM_KIND = [opt("school_class", "Class", "कक्षा"), opt("course", "Course", "पाठ्यक्रम"), opt("batch", "Batch", "बैच")];
const ATT_STATUS = [
  opt("present", "Present", "उपस्थित"), opt("absent", "Absent", "अनुपस्थित"), opt("leave", "Leave", "अवकाश"),
  opt("late", "Late", "विलंब"), opt("half_day", "Half-day", "आधा दिन"),
];
export const ROLE = [
  opt("admin", "Admin", "प्रशासक"), opt("group_admin", "Group admin", "समूह प्रशासक"), opt("accountant", "Accountant", "लेखाकार"),
  opt("teacher", "Teacher", "शिक्षक"), opt("librarian", "Librarian", "पुस्तकालयाध्यक्ष"), opt("warden", "Warden", "वार्डन"),
  opt("transport", "Transport in-charge", "परिवहन प्रभारी"), opt("hr", "HR", "मानव संसाधन"), opt("store", "Store keeper", "भंडारपाल"),
];

const STUDENT_REL = { resource: "people/students", label: "full_name", search: true };
const STAFF_REL = { resource: "people/staff", label: "full_name", search: true };

export const MODULES: ModuleDef[] = [
  { key: "people", label: t("Students & Staff", "छात्र एवं कर्मचारी"), icon: "TeamOutlined" },
  { key: "library", label: t("Library", "पुस्तकालय"), icon: "BookOutlined" },
  { key: "hostel", label: t("Hostel & Mess", "छात्रावास एवं मेस"), icon: "HomeOutlined" },
  { key: "attendance", label: t("Attendance", "उपस्थिति"), icon: "CheckSquareOutlined" },
  { key: "exam", label: t("Exam", "परीक्षा"), icon: "FileDoneOutlined" },
  { key: "fees", label: t("Fees", "शुल्क"), icon: "WalletOutlined" },
  { key: "payroll", label: t("Payroll", "वेतन"), icon: "BankOutlined" },
  { key: "transport", label: t("Transport", "परिवहन"), icon: "CarOutlined" },
  { key: "inventory", label: t("Inventory", "भंडार"), icon: "InboxOutlined" },
  { key: "org", label: t("Settings", "सेटिंग्स"), icon: "SettingOutlined" },
];

export const RESOURCES: ResourceDef[] = [
  // ------------------------------------------------------------ people
  {
    name: "people/students", module: "people", label: t("Students", "छात्र"), perm: "people.student",
    searchable: true, importable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: STUDENT_STATUS }],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं."), sorter: true },
      { key: "full_name", label: t("Name", "नाम"), sorter: true },
      { key: "current_program", label: t("Class / course", "कक्षा / पाठ्यक्रम") },
      { key: "current_section", label: t("Section", "अनुभाग") },
      { key: "primary_guardian.name", label: t("Guardian", "अभिभावक") },
      { key: "primary_guardian.phone", label: t("Guardian phone", "अभिभावक फ़ोन") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: STUDENT_STATUS },
    ],
    fields: [
      { name: "admission_no", label: t("Admission no.", "प्रवेश सं."), type: "text", required: true },
      { name: "full_name", label: t("Full name", "पूरा नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "date_of_birth", label: t("Date of birth", "जन्म तिथि"), type: "date" },
      { name: "gender", label: t("Gender", "लिंग"), type: "select", options: GENDER },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text" },
      { name: "email", label: t("Email", "ईमेल"), type: "email" },
      { name: "address", label: t("Address", "पता"), type: "textarea" },
      { name: "admission_date", label: t("Admission date", "प्रवेश तिथि"), type: "date" },
      { name: "status", label: t("Status", "स्थिति"), type: "select", options: STUDENT_STATUS },
    ],
  },
  {
    name: "people/enrollments", module: "people", label: t("Class enrolments", "कक्षा नामांकन"), perm: "people.enrollment",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [
      { field: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), relation: { resource: "people/programs", label: "name" } },
      { field: "section", label: t("Section", "अनुभाग"), relation: { resource: "people/sections", label: "name" } },
    ],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "program_name", label: t("Class / course", "कक्षा / पाठ्यक्रम") },
      { key: "section_name", label: t("Section", "अनुभाग") },
      { key: "roll_no", label: t("Roll no.", "अनुक्रमांक") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "academic_year", label: t("Academic year", "शैक्षणिक वर्ष"), type: "relation", relation: { resource: "people/academic-years", label: "name" }, required: true },
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" }, required: true },
      { name: "term", label: t("Term / semester", "सत्र / सेमेस्टर"), type: "relation", relation: { resource: "people/terms", label: "name" } },
      { name: "section", label: t("Section", "अनुभाग"), type: "relation", relation: { resource: "people/sections", label: "name" } },
      { name: "roll_no", label: t("Roll no.", "अनुक्रमांक"), type: "text" },
    ],
  },
  {
    name: "people/staff", module: "people", label: t("Staff", "कर्मचारी"), perm: "people.staff",
    searchable: true, importable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: STAFF_STATUS }],
    columns: [
      { key: "employee_code", label: t("Employee code", "कर्मचारी कोड"), sorter: true },
      { key: "full_name", label: t("Name", "नाम"), sorter: true },
      { key: "designation", label: t("Designation", "पद") },
      { key: "department_name", label: t("Department", "विभाग") },
      { key: "phone", label: t("Phone", "फ़ोन") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: STAFF_STATUS },
    ],
    fields: [
      { name: "employee_code", label: t("Employee code", "कर्मचारी कोड"), type: "text", required: true },
      { name: "full_name", label: t("Full name", "पूरा नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "designation", label: t("Designation", "पद"), type: "text" },
      { name: "department", label: t("Department", "विभाग"), type: "relation", relation: { resource: "people/departments", label: "name" } },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text" },
      { name: "email", label: t("Email", "ईमेल"), type: "email" },
      { name: "date_of_birth", label: t("Date of birth", "जन्म तिथि"), type: "date" },
      { name: "date_joined", label: t("Date of joining", "कार्यग्रहण तिथि"), type: "date" },
      { name: "employment_type", label: t("Employment type", "रोज़गार प्रकार"), type: "select", options: EMPLOYMENT },
      { name: "status", label: t("Status", "स्थिति"), type: "select", options: STAFF_STATUS },
    ],
  },
  {
    name: "people/guardians", module: "people", label: t("Guardians", "अभिभावक"), perm: "people.guardian",
    searchable: true, canCreate: true, canEdit: true,
    columns: [
      { key: "full_name", label: t("Name", "नाम") },
      { key: "phone", label: t("Phone", "फ़ोन") },
      { key: "email", label: t("Email", "ईमेल") },
      { key: "occupation", label: t("Occupation", "व्यवसाय") },
    ],
    fields: [
      { name: "full_name", label: t("Full name", "पूरा नाम"), type: "text", required: true },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text", required: true },
      { name: "alt_phone", label: t("Alternate phone", "वैकल्पिक फ़ोन"), type: "text" },
      { name: "email", label: t("Email", "ईमेल"), type: "email" },
      { name: "occupation", label: t("Occupation", "व्यवसाय"), type: "text" },
      { name: "address", label: t("Address", "पता"), type: "textarea" },
    ],
  },
  {
    name: "people/programs", module: "people", label: t("Classes & courses", "कक्षाएँ एवं पाठ्यक्रम"), perm: "people.program",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "code", label: t("Code", "कोड") },
      { key: "name", label: t("Name", "नाम") },
      { key: "kind", label: t("Type", "प्रकार"), type: "tag", options: PROGRAM_KIND },
      { key: "sequence", label: t("Order", "क्रम"), type: "number", sorter: true },
    ],
    fields: [
      { name: "code", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "kind", label: t("Type", "प्रकार"), type: "select", options: PROGRAM_KIND },
      { name: "sequence", label: t("Order", "क्रम"), type: "number" },
    ],
  },
  {
    name: "people/sections", module: "people", label: t("Sections & batches", "अनुभाग एवं बैच"), perm: "people.section",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "program_name", label: t("Class / course", "कक्षा / पाठ्यक्रम") },
      { key: "name", label: t("Section", "अनुभाग") },
      { key: "class_teacher_name", label: t("Class teacher", "कक्षा शिक्षक") },
      { key: "student_count", label: t("Students", "छात्र"), type: "number" },
      { key: "capacity", label: t("Capacity", "क्षमता"), type: "number" },
    ],
    fields: [
      { name: "academic_year", label: t("Academic year", "शैक्षणिक वर्ष"), type: "relation", relation: { resource: "people/academic-years", label: "name" }, required: true },
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" }, required: true },
      { name: "term", label: t("Term / semester", "सत्र / सेमेस्टर"), type: "relation", relation: { resource: "people/terms", label: "name" } },
      { name: "name", label: t("Section name", "अनुभाग नाम"), type: "text", required: true },
      { name: "class_teacher", label: t("Class teacher", "कक्षा शिक्षक"), type: "relation", relation: STAFF_REL },
      { name: "capacity", label: t("Capacity", "क्षमता"), type: "number" },
    ],
  },
  {
    name: "people/terms", module: "people", label: t("Terms & semesters", "सत्र एवं सेमेस्टर"), perm: "people.term",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "program", label: t("Class / course id", "कक्षा / पाठ्यक्रम") },
      { key: "name", label: t("Name", "नाम") },
      { key: "sequence", label: t("Order", "क्रम"), type: "number" },
    ],
    fields: [
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" }, required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "sequence", label: t("Order", "क्रम"), type: "number", required: true },
    ],
  },
  {
    name: "people/subjects", module: "people", label: t("Subjects", "विषय"), perm: "people.subject",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "code", label: t("Code", "कोड") },
      { key: "name", label: t("Name", "नाम") },
      { key: "credits", label: t("Credits", "क्रेडिट"), type: "number" },
      { key: "has_practical", label: t("Practical", "प्रायोगिक"), type: "bool" },
    ],
    fields: [
      { name: "code", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" } },
      { name: "term", label: t("Term / semester", "सत्र / सेमेस्टर"), type: "relation", relation: { resource: "people/terms", label: "name" } },
      { name: "credits", label: t("Credits (colleges)", "क्रेडिट (महाविद्यालय)"), type: "number" },
      { name: "has_practical", label: t("Has practical", "प्रायोगिक है"), type: "boolean" },
    ],
  },
  {
    name: "people/academic-years", module: "people", label: t("Academic years", "शैक्षणिक वर्ष"), perm: "people.academic_year",
    canCreate: true, canEdit: true,
    columns: [
      { key: "name", label: t("Year", "वर्ष") },
      { key: "start_date", label: t("Starts", "आरंभ"), type: "date" },
      { key: "end_date", label: t("Ends", "समाप्ति"), type: "date" },
      { key: "is_current", label: t("Current", "वर्तमान"), type: "bool" },
    ],
    fields: [
      { name: "name", label: t("Year (e.g. 2026-27)", "वर्ष (उदा. 2026-27)"), type: "text", required: true },
      { name: "start_date", label: t("Starts", "आरंभ"), type: "date", required: true },
      { name: "end_date", label: t("Ends", "समाप्ति"), type: "date", required: true },
      { name: "is_current", label: t("Current year", "वर्तमान वर्ष"), type: "boolean" },
    ],
  },
  {
    name: "people/departments", module: "people", label: t("Departments", "विभाग"), perm: "people.department",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [{ key: "name", label: t("Name", "नाम") }],
    fields: [{ name: "name", label: t("Name", "नाम"), type: "text", required: true }],
  },

  // ------------------------------------------------------------ library
  {
    name: "library/books", module: "library", label: t("Books", "पुस्तकें"), perm: "library.book",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "title", label: t("Title", "शीर्षक"), sorter: true },
      { key: "author", label: t("Author", "लेखक") },
      { key: "isbn", label: t("ISBN", "ISBN") },
      { key: "category_name", label: t("Category", "श्रेणी") },
      { key: "shelf_location", label: t("Shelf", "रैक") },
      { key: "copies_available", label: t("Available", "उपलब्ध"), type: "number", sorter: true },
      { key: "copies_total", label: t("Total", "कुल"), type: "number" },
    ],
    fields: [
      { name: "title", label: t("Title", "शीर्षक"), type: "text", required: true },
      { name: "author", label: t("Author", "लेखक"), type: "text", required: true },
      { name: "isbn", label: t("ISBN", "ISBN"), type: "text", required: true },
      { name: "barcode", label: t("Barcode", "बारकोड"), type: "text" },
      { name: "publisher", label: t("Publisher", "प्रकाशक"), type: "text" },
      { name: "published_year", label: t("Year", "वर्ष"), type: "number" },
      { name: "category", label: t("Category", "श्रेणी"), type: "relation", relation: { resource: "library/categories", label: "name" } },
      { name: "shelf_location", label: t("Shelf", "रैक"), type: "text" },
      { name: "copies_total", label: t("Copies", "प्रतियाँ"), type: "number", required: true },
    ],
  },
  {
    name: "library/members", module: "library", label: t("Members", "सदस्य"), perm: "library.member",
    searchable: true, canCreate: true, canEdit: true,
    columns: [
      { key: "full_name", label: t("Name", "नाम") },
      { key: "member_type", label: t("Type", "प्रकार"), type: "tag", options: [opt("student", "Student", "छात्र"), opt("staff", "Staff", "कर्मचारी")] },
      { key: "phone", label: t("Phone", "फ़ोन") },
      { key: "open_loan_count", label: t("Books out", "जारी पुस्तकें"), type: "number" },
      { key: "effective_borrow_limit", label: t("Limit", "सीमा"), type: "number" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, createOnly: true, help: t("Choose a student or a staff member", "छात्र या कर्मचारी चुनें") },
      { name: "staff", label: t("Staff member", "कर्मचारी"), type: "relation", relation: STAFF_REL, createOnly: true },
      { name: "max_books", label: t("Borrowing limit (blank = default)", "सीमा (खाली = डिफ़ॉल्ट)"), type: "number" },
    ],
  },
  {
    name: "library/issues", module: "library", label: t("Issue & return", "जारी एवं वापसी"), perm: "library.issue",
    canCreate: true,
    filters: [{ field: "open", label: t("Open loans", "जारी पुस्तकें"), options: [opt("true", "Open", "जारी"), opt("false", "Returned", "वापस")] },
              { field: "overdue", label: t("Overdue", "विलंबित"), options: [opt("true", "Overdue", "विलंबित")] }],
    columns: [
      { key: "book_title", label: t("Book", "पुस्तक") },
      { key: "member_name", label: t("Member", "सदस्य") },
      { key: "due_date", label: t("Due", "नियत तिथि"), type: "date", sorter: true },
      { key: "is_overdue", label: t("Overdue", "विलंबित"), type: "bool" },
      { key: "renewals", label: t("Renewals", "नवीनीकरण"), type: "number" },
      { key: "returned_at", label: t("Returned", "वापस"), type: "datetime" },
    ],
    fields: [
      { name: "book", label: t("Book", "पुस्तक"), type: "relation", relation: { resource: "library/books", label: "title", search: true }, required: true },
      { name: "member", label: t("Member", "सदस्य"), type: "relation", relation: { resource: "library/members", label: "full_name", search: true }, required: true },
    ],
    actions: [
      { key: "return", label: t("Return", "वापसी"), perm: "library.issue.return", method: "post", path: "return", visibleWhen: { field: "returned_at", equals: null } },
      { key: "renew", label: t("Renew", "नवीनीकरण"), perm: "library.issue.renew", method: "post", path: "renew", visibleWhen: { field: "returned_at", equals: null } },
    ],
  },
  {
    name: "library/fines", module: "library", label: t("Fines", "जुर्माना"), perm: "library.fine",
    filters: [{ field: "paid", label: t("Paid", "भुगतान"), options: [opt("true", "Paid", "भुगतान"), opt("false", "Unpaid", "बकाया")] }],
    columns: [
      { key: "member", label: t("Member id", "सदस्य") },
      { key: "amount", label: t("Amount", "राशि"), type: "money", sorter: true },
      { key: "reason", label: t("Reason", "कारण") },
      { key: "paid", label: t("Paid", "भुगतान"), type: "bool" },
      { key: "waived", label: t("Waived", "माफ़"), type: "bool" },
      { key: "created_at", label: t("Date", "तिथि"), type: "date", sorter: true },
    ],
    actions: [
      { key: "pay", label: t("Mark paid", "भुगतान दर्ज करें"), perm: "library.fine.manage", method: "patch", path: "", body: { paid: true }, visibleWhen: { field: "paid", equals: false } },
      { key: "waive", label: t("Waive", "माफ़ करें"), perm: "library.fine.waive", method: "post", path: "waive", confirm: t("Waive this fine?", "यह जुर्माना माफ़ करें?"), danger: true, visibleWhen: { field: "waived", equals: false } },
    ],
  },
  {
    name: "library/holds", module: "library", label: t("Reservations", "आरक्षण"), perm: "library.hold",
    canCreate: true, canDelete: true, deleteLabel: t("Cancel", "रद्द करें"),
    columns: [
      { key: "book", label: t("Book id", "पुस्तक") },
      { key: "member", label: t("Member id", "सदस्य") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "created_at", label: t("Reserved", "आरक्षित"), type: "datetime" },
    ],
    fields: [
      { name: "book", label: t("Book", "पुस्तक"), type: "relation", relation: { resource: "library/books", label: "title", search: true }, required: true },
      { name: "member", label: t("Member", "सदस्य"), type: "relation", relation: { resource: "library/members", label: "full_name", search: true }, required: true },
    ],
  },
  {
    name: "library/categories", module: "library", label: t("Categories", "श्रेणियाँ"), perm: "library.category",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [{ key: "name", label: t("Name", "नाम") }],
    fields: [{ name: "name", label: t("Name", "नाम"), type: "text", required: true }],
  },

  // ------------------------------------------------------------ hostel
  {
    name: "hostel/rooms", module: "hostel", label: t("Rooms", "कमरे"), perm: "hostel.room",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "number", label: t("Room", "कमरा"), sorter: true },
      { key: "room_type", label: t("Type", "प्रकार"), type: "tag" },
      { key: "gender", label: t("For", "हेतु"), type: "tag" },
      { key: "floor", label: t("Floor", "तल"), type: "number" },
      { key: "capacity", label: t("Beds", "बिस्तर"), type: "number" },
      { key: "occupied", label: t("Occupied", "भरे"), type: "number" },
      { key: "available_beds", label: t("Free", "खाली"), type: "number" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
    ],
    fields: [
      { name: "number", label: t("Room number", "कमरा संख्या"), type: "text", required: true },
      { name: "capacity", label: t("Beds", "बिस्तर"), type: "number", required: true },
      { name: "room_type", label: t("Type", "प्रकार"), type: "select", options: [opt("single", "Single", "एकल"), opt("double", "Double", "दोहरा"), opt("dorm", "Dormitory", "छात्रावास कक्ष")] },
      { name: "gender", label: t("For", "हेतु"), type: "select", options: [opt("male", "Boys", "छात्र"), opt("female", "Girls", "छात्राएँ"), opt("any", "Any", "कोई भी")] },
      { name: "floor", label: t("Floor", "तल"), type: "number" },
      { name: "status", label: t("Status", "स्थिति"), type: "select", options: [opt("active", "Active", "सक्रिय"), opt("maintenance", "Under repair", "मरम्मत में"), opt("decommissioned", "Closed", "बंद")] },
    ],
  },
  {
    name: "hostel/allocations", module: "hostel", label: t("Allocations", "आवंटन"), perm: "hostel.allocation",
    canCreate: true,
    filters: [{ field: "active", label: t("Current", "वर्तमान"), options: [opt("true", "Current", "वर्तमान"), opt("false", "Past", "पूर्व")] }],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "room_number", label: t("Room", "कमरा") },
      { key: "check_in_date", label: t("Check-in", "प्रवेश"), type: "date", sorter: true },
      { key: "check_out_date", label: t("Check-out", "प्रस्थान"), type: "date" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "room", label: t("Room", "कमरा"), type: "relation", relation: { resource: "hostel/rooms", label: "number", search: true }, required: true },
    ],
    actions: [
      { key: "vacate", label: t("Vacate", "खाली करें"), perm: "hostel.allocation.vacate", method: "post", path: "vacate", confirm: t("Vacate this bed?", "यह बिस्तर खाली करें?"), visibleWhen: { field: "check_out_date", equals: null } },
    ],
  },
  {
    name: "hostel/waitlist", module: "hostel", label: t("Waiting list", "प्रतीक्षा सूची"), perm: "hostel.waitlist",
    canCreate: true, canDelete: true, deleteLabel: t("Cancel", "रद्द करें"),
    columns: [
      { key: "student", label: t("Student id", "छात्र") },
      { key: "room", label: t("Room id", "कमरा") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "created_at", label: t("Added", "जोड़ा गया"), type: "datetime" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "room", label: t("Room", "कमरा"), type: "relation", relation: { resource: "hostel/rooms", label: "number" }, required: true },
    ],
  },
  {
    name: "hostel/maintenance", module: "hostel", label: t("Repairs", "मरम्मत"), perm: "hostel.maintenance",
    canCreate: true,
    columns: [
      { key: "room", label: t("Room id", "कमरा") },
      { key: "summary", label: t("Problem", "समस्या") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "created_at", label: t("Raised", "दर्ज"), type: "datetime" },
      { key: "closed_at", label: t("Closed", "बंद"), type: "datetime" },
    ],
    fields: [
      { name: "room", label: t("Room", "कमरा"), type: "relation", relation: { resource: "hostel/rooms", label: "number" }, required: true },
      { name: "summary", label: t("Problem", "समस्या"), type: "text", required: true },
      { name: "details", label: t("Details", "विवरण"), type: "textarea" },
    ],
    actions: [
      { key: "close", label: t("Close", "बंद करें"), perm: "hostel.maintenance.manage", method: "post", path: "close", visibleWhen: { field: "status", equals: "open" } },
    ],
  },

  // ------------------------------------------------------------ attendance
  {
    name: "attendance/records", module: "attendance", label: t("Attendance records", "उपस्थिति अभिलेख"), perm: "attendance.record",
    canCreate: true, createEndpoint: "attendance/records/mark",
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: ATT_STATUS }],
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "period", label: t("Lecture", "व्याख्यान"), type: "number" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: ATT_STATUS },
      { key: "marked_by", label: t("Marked by", "द्वारा") },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "date", label: t("Date", "तिथि"), type: "date", required: true },
      { name: "status", label: t("Status", "स्थिति"), type: "select", options: ATT_STATUS, required: true },
      { name: "period", label: t("Lecture no. (colleges)", "व्याख्यान सं. (महाविद्यालय)"), type: "number" },
    ],
  },

  // ------------------------------------------------------------ exam
  {
    name: "exam/results", module: "exam", label: t("Marks", "अंक"), perm: "exam.result",
    canCreate: true, createEndpoint: "exam/results/record",
    columns: [
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "subject_name", label: t("Subject", "विषय") },
      { key: "exam_name", label: t("Exam", "परीक्षा") },
      { key: "marks_obtained", label: t("Marks", "अंक"), type: "number" },
      { key: "max_marks", label: t("Out of", "पूर्णांक"), type: "number" },
      { key: "percentage", label: t("%", "%"), type: "number" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "subject", label: t("Subject", "विषय"), type: "relation", relation: { resource: "people/subjects", label: "name", search: true }, required: true },
      { name: "exam_name", label: t("Exam", "परीक्षा"), type: "text", required: true },
      { name: "marks_obtained", label: t("Marks", "अंक"), type: "number", required: true },
      { name: "max_marks", label: t("Out of", "पूर्णांक"), type: "number" },
    ],
  },

  // ------------------------------------------------------------ fees
  {
    name: "fees/structures", module: "fees", label: t("Fee structures", "शुल्क संरचना"), perm: "fees.structure",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "name", label: t("Name", "नाम") },
      { key: "term", label: t("Term", "सत्र") },
      { key: "amount", label: t("Amount", "राशि"), type: "money", sorter: true },
      { key: "due_date", label: t("Due", "नियत तिथि"), type: "date", sorter: true },
    ],
    fields: [
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "term", label: t("Term", "सत्र"), type: "text" },
      { name: "amount", label: t("Amount (₹)", "राशि (₹)"), type: "money", required: true },
      { name: "due_date", label: t("Due date", "नियत तिथि"), type: "date" },
    ],
  },
  {
    name: "fees/payments", module: "fees", label: t("Collections", "संग्रह"), perm: "fees.payment",
    searchable: true, canCreate: true,
    columns: [
      { key: "receipt_no", label: t("Receipt no.", "रसीद सं.") },
      { key: "payer_name", label: t("Paid by", "भुगतानकर्ता") },
      { key: "payer_reference", label: t("Admission / roll no.", "प्रवेश / अनुक्रमांक") },
      { key: "amount", label: t("Amount", "राशि"), type: "money", sorter: true },
      { key: "created_at", label: t("Date", "तिथि"), type: "datetime", sorter: true },
    ],
    fields: [
      { name: "fee_structure", label: t("Fee", "शुल्क"), type: "relation", relation: { resource: "fees/structures", label: "name" }, required: true },
      { name: "payer_name", label: t("Paid by", "भुगतानकर्ता"), type: "text", required: true },
      { name: "payer_reference", label: t("Admission / roll no.", "प्रवेश / अनुक्रमांक"), type: "text" },
      { name: "amount", label: t("Amount (₹)", "राशि (₹)"), type: "money", required: true },
    ],
  },

  // ------------------------------------------------------------ payroll
  {
    name: "payroll/payslips", module: "payroll", label: t("Payslips", "वेतन पर्ची"), perm: "payroll.payslip",
    canCreate: true,
    columns: [
      { key: "staff_name", label: t("Staff", "कर्मचारी") },
      { key: "period", label: t("Month", "माह"), type: "date", sorter: true },
      { key: "basic_salary", label: t("Basic", "मूल वेतन"), type: "money" },
      { key: "allowances", label: t("Allowances", "भत्ते"), type: "money" },
      { key: "deductions", label: t("Deductions", "कटौती"), type: "money" },
      { key: "net_pay", label: t("Net pay", "शुद्ध वेतन"), type: "money" },
    ],
    fields: [
      { name: "staff", label: t("Staff", "कर्मचारी"), type: "relation", relation: STAFF_REL, required: true },
      { name: "period", label: t("Month (any date in it)", "माह (कोई भी तिथि)"), type: "date", required: true },
      { name: "basic_salary", label: t("Basic (₹)", "मूल वेतन (₹)"), type: "money", required: true },
      { name: "allowances", label: t("Allowances (₹)", "भत्ते (₹)"), type: "money" },
      { name: "deductions", label: t("Deductions (₹)", "कटौती (₹)"), type: "money" },
    ],
  },

  // ------------------------------------------------------------ transport
  {
    name: "transport/routes", module: "transport", label: t("Routes", "मार्ग"), perm: "transport.route",
    canCreate: true, canEdit: true, canDelete: true,
    columns: [{ key: "name", label: t("Route", "मार्ग") }, { key: "stops", label: t("Stops", "पड़ाव") }],
    fields: [
      { name: "name", label: t("Route name", "मार्ग नाम"), type: "text", required: true },
      { name: "stops", label: t("Stops (one per line)", "पड़ाव (हर पंक्ति में एक)"), type: "textarea" },
    ],
  },
  {
    name: "transport/vehicles", module: "transport", label: t("Vehicles", "वाहन"), perm: "transport.vehicle",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "number", label: t("Registration no.", "पंजीकरण सं.") },
      { key: "route_name", label: t("Route", "मार्ग") },
      { key: "capacity", label: t("Seats", "सीटें"), type: "number" },
      { key: "active_riders", label: t("Riders", "यात्री"), type: "number" },
      { key: "available_seats", label: t("Free seats", "खाली सीटें"), type: "number" },
    ],
    fields: [
      { name: "number", label: t("Registration no.", "पंजीकरण सं."), type: "text", required: true },
      { name: "capacity", label: t("Seats", "सीटें"), type: "number", required: true },
      { name: "route", label: t("Route", "मार्ग"), type: "relation", relation: { resource: "transport/routes", label: "name" } },
    ],
  },
  {
    name: "transport/assignments", module: "transport", label: t("Riders", "यात्री"), perm: "transport.assignment",
    canCreate: true,
    columns: [
      { key: "rider_name", label: t("Rider", "यात्री") },
      { key: "rider_contact", label: t("Contact", "संपर्क") },
      { key: "pickup_point", label: t("Pick-up", "पिक-अप") },
      { key: "vehicle", label: t("Vehicle id", "वाहन") },
      { key: "removed_at", label: t("Stopped", "बंद"), type: "datetime" },
    ],
    fields: [
      { name: "vehicle", label: t("Vehicle", "वाहन"), type: "relation", relation: { resource: "transport/vehicles", label: "number" }, required: true },
      { name: "rider_name", label: t("Rider", "यात्री"), type: "text", required: true },
      { name: "rider_contact", label: t("Contact", "संपर्क"), type: "text" },
      { name: "pickup_point", label: t("Pick-up point", "पिक-अप स्थान"), type: "text" },
    ],
    actions: [
      { key: "unassign", label: t("Stop transport", "परिवहन बंद करें"), perm: "transport.assignment.manage", method: "post", path: "unassign", confirm: t("Stop transport for this rider?", "इस यात्री का परिवहन बंद करें?"), visibleWhen: { field: "removed_at", equals: null } },
    ],
  },

  // ------------------------------------------------------------ inventory
  {
    name: "inventory/items", module: "inventory", label: t("Items", "सामग्री"), perm: "inventory.item",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "sku", label: t("Code", "कोड") },
      { key: "name", label: t("Item", "सामग्री"), sorter: true },
      { key: "category", label: t("Category", "श्रेणी") },
      { key: "quantity_available", label: t("In stock", "स्टॉक"), type: "number", sorter: true },
      { key: "quantity_total", label: t("Total", "कुल"), type: "number" },
    ],
    fields: [
      { name: "sku", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Item", "सामग्री"), type: "text", required: true },
      { name: "category", label: t("Category", "श्रेणी"), type: "text" },
      { name: "quantity_total", label: t("Quantity", "मात्रा"), type: "number", required: true },
    ],
  },
  {
    name: "inventory/issues", module: "inventory", label: t("Issue & return", "जारी एवं वापसी"), perm: "inventory.issue",
    canCreate: true,
    columns: [
      { key: "item_name", label: t("Item", "सामग्री") },
      { key: "issued_to", label: t("Issued to", "प्राप्तकर्ता") },
      { key: "created_at", label: t("Issued", "जारी"), type: "datetime", sorter: true },
      { key: "returned_at", label: t("Returned", "वापस"), type: "datetime" },
    ],
    fields: [
      { name: "item", label: t("Item", "सामग्री"), type: "relation", relation: { resource: "inventory/items", label: "name", search: true }, required: true },
      { name: "issued_to", label: t("Issued to", "प्राप्तकर्ता"), type: "text", required: true },
    ],
    actions: [
      { key: "return", label: t("Return", "वापसी"), perm: "inventory.issue.manage", method: "post", path: "return", visibleWhen: { field: "returned_at", equals: null } },
    ],
  },

  // ------------------------------------------------------------ settings
  {
    name: "org/users", module: "org", label: t("Users & roles", "उपयोगकर्ता एवं भूमिकाएँ"), perm: "org.user",
    searchable: true, canCreate: true, canEdit: true,
    columns: [
      { key: "email", label: t("Email", "ईमेल") },
      { key: "first_name", label: t("First name", "नाम") },
      { key: "last_name", label: t("Last name", "उपनाम") },
      { key: "phone", label: t("Phone", "फ़ोन") },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "email", label: t("Email (login)", "ईमेल (लॉगिन)"), type: "email", required: true },
      { name: "first_name", label: t("First name", "नाम"), type: "text" },
      { name: "last_name", label: t("Last name", "उपनाम"), type: "text" },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text" },
      { name: "preferred_language", label: t("Language", "भाषा"), type: "select", options: [opt("en", "English", "English"), opt("hi", "हिन्दी", "हिन्दी")] },
      { name: "roles", label: t("Roles in this branch", "इस शाखा में भूमिकाएँ"), type: "multiselect", options: ROLE },
      { name: "password", label: t("Password (min 10 characters)", "पासवर्ड (कम से कम 10 अक्षर)"), type: "password" },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean", editOnly: true },
    ],
  },
  {
    name: "org/branches", module: "org", label: t("Branches", "शाखाएँ"), perm: "org.branch",
    canCreate: true, canEdit: true,
    columns: [
      { key: "code", label: t("Code", "कोड") },
      { key: "name", label: t("Name", "नाम") },
      { key: "phone", label: t("Phone", "फ़ोन") },
      { key: "email", label: t("Email", "ईमेल") },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "code", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "address", label: t("Address", "पता"), type: "textarea" },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text" },
      { name: "email", label: t("Email", "ईमेल"), type: "email" },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean" },
    ],
  },
];

export function findResource(module: string, resource: string): ResourceDef | undefined {
  return RESOURCES.find((r) => r.name === `${module}/${resource}`);
}

export const tr = (text: T, lang: "en" | "hi") => text[lang] || text.en;
