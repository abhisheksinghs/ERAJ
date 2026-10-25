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
  | "select" | "multiselect" | "relation" | "boolean" | "rows";

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
  rowFields?: FieldDef[]; // for type "rows": an editable table of sub-records (e.g. instalments)
  addLabel?: T;
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
  method: "post" | "patch" | "link";
  path: string; // relative to the resource item, e.g. "return" → <resource>/<id>/return/
  href?: string; // method "link": URL with {id}, e.g. "/api/proxy/fees/receipts/{id}/pdf"
  newTab?: boolean;
  prompt?: { field: string; label: T }; // ask for a value (e.g. a reason) and send it in the body
  body?: Record<string, unknown>;
  confirm?: T;
  danger?: boolean;
  visibleWhen?: { field: string; equals: unknown };
}

export interface FilterDef {
  field: string;
  label: T;
  options?: Option[];
  relation?: { resource: string; label: string; search?: boolean };
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
  exportable?: boolean; // Excel/CSV download of the filtered list (default true)
  defaultSort?: { field: string; order: "asc" | "desc" };
}

/** Hand-built screens (not generated from a registry entry). */
export interface PageDef {
  name: string; // menu identifier, e.g. "fees/collect"
  module: string;
  label: T;
  perm: string; // full permission, e.g. "fees.receipt.manage"
  path: string;
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

const HOSTEL_GENDER = [opt("male", "Boys", "छात्र"), opt("female", "Girls", "छात्राएँ"), opt("any", "Any", "कोई भी")];
const ROOM_TYPE = [opt("single", "Single", "एकल"), opt("double", "Double", "दोहरा"), opt("triple", "Triple", "तिहरा"), opt("dorm", "Dormitory", "डॉरमिटरी")];
const ROOM_STATUS = [opt("active", "Active", "सक्रिय"), opt("repair", "Under repair", "मरम्मत में"), opt("closed", "Closed", "बंद")];
const MESS_PLAN = [opt("monthly", "Fixed monthly", "निश्चित मासिक"), opt("per_day", "Per day", "प्रति दिन")];
const MEAL = [opt("breakfast", "Breakfast", "नाश्ता"), opt("lunch", "Lunch", "दोपहर का भोजन"), opt("snacks", "Evening snacks", "शाम का नाश्ता"), opt("dinner", "Dinner", "रात का भोजन")];
const WEEKDAY = [opt("0", "Monday", "सोमवार"), opt("1", "Tuesday", "मंगलवार"), opt("2", "Wednesday", "बुधवार"), opt("3", "Thursday", "गुरुवार"), opt("4", "Friday", "शुक्रवार"), opt("5", "Saturday", "शनिवार"), opt("6", "Sunday", "रविवार")];
const COMPLAINT_CATEGORY = [opt("quality", "Food quality", "भोजन गुणवत्ता"), opt("hygiene", "Hygiene", "स्वच्छता"), opt("timing", "Timing", "समय"), opt("quantity", "Quantity", "मात्रा"), opt("other", "Other", "अन्य")];
const VISIT_STATUS = [opt("held", "Waiting for warden", "वार्डन की प्रतीक्षा"), opt("in", "Inside", "अंदर"), opt("out", "Left", "चले गए"), opt("refused", "Refused", "मना")];
const OUTPASS_STATUS = [opt("requested", "Requested", "अनुरोधित"), opt("approved", "Approved", "स्वीकृत"), opt("rejected", "Rejected", "अस्वीकृत"), opt("out", "Out", "बाहर"), opt("returned", "Returned", "लौटे"), opt("cancelled", "Cancelled", "रद्द")];

const ATT_MODE = [opt("daily", "Once a day", "दिन में एक बार"), opt("per_lecture", "Per lecture / subject", "प्रति व्याख्यान")];
const DEVICE_BRAND = [
  opt("zkteco", "ZKTeco (ADMS push)", "ZKTeco"), opt("essl", "eSSL (ADMS push)", "eSSL"), opt("realtime", "Realtime (ADMS push)", "Realtime"),
  opt("identix", "Identix (ADMS push)", "Identix"), opt("generic", "Other — JSON push", "अन्य — JSON"), opt("file", "Other — Excel/CSV import", "अन्य — फ़ाइल आयात"),
];
const SCALE_KIND = [opt("marks", "Marks → grade (school)", "अंक → ग्रेड (विद्यालय)"), opt("credit", "Credits → SGPA/CGPA (college)", "क्रेडिट → SGPA/CGPA")];
const SECTION_REL = { resource: "people/sections", label: "label" };

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
      { field: "section", label: t("Section", "अनुभाग"), relation: SECTION_REL },
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
      { name: "section", label: t("Section", "अनुभाग"), type: "relation", relation: SECTION_REL },
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
    name: "people/teaching", module: "people", label: t("Teaching allocation", "शिक्षण आवंटन"), perm: "people.teaching",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "section", label: t("Section", "अनुभाग"), relation: SECTION_REL }],
    columns: [
      { key: "section_name", label: t("Section", "अनुभाग") },
      { key: "subject_name", label: t("Subject", "विषय") },
      { key: "staff_name", label: t("Teacher", "शिक्षक") },
      { key: "periods_per_week", label: t("Periods / week", "कालांश / सप्ताह"), type: "number" },
    ],
    fields: [
      { name: "section", label: t("Section", "अनुभाग"), type: "relation", relation: { ...SECTION_REL, search: true }, required: true },
      { name: "subject", label: t("Subject", "विषय"), type: "relation", relation: { resource: "people/subjects", label: "name", search: true }, required: true },
      { name: "staff", label: t("Teacher", "शिक्षक"), type: "relation", relation: STAFF_REL, required: true },
      { name: "periods_per_week", label: t("Periods per week", "प्रति सप्ताह कालांश"), type: "number" },
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
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: [opt("open", "Unpaid", "बकाया"), opt("paid", "Paid", "भुगतान"), opt("waived", "Waived", "माफ़")] }],
    columns: [
      { key: "member_name", label: t("Member", "सदस्य") },
      { key: "book_title", label: t("Book", "पुस्तक") },
      { key: "amount", label: t("Amount", "राशि"), type: "money", sorter: true },
      { key: "reason", label: t("Reason", "कारण") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: [opt("open", "Unpaid", "बकाया"), opt("paid", "Paid", "भुगतान"), opt("waived", "Waived", "माफ़")] },
      { key: "in_fees", label: t("On fee account", "शुल्क खाते में"), type: "bool" },
      { key: "created_at", label: t("Date", "तिथि"), type: "date", sorter: true },
    ],
    actions: [
      { key: "pay", label: t("Mark paid", "भुगतान दर्ज करें"), perm: "library.fine.manage", method: "patch", path: "", body: { paid: true }, visibleWhen: { field: "can_mark_paid", equals: true } },
      { key: "waive", label: t("Waive", "माफ़ करें"), perm: "library.fine.waive", method: "post", path: "waive", confirm: t("Waive this fine?", "यह जुर्माना माफ़ करें?"), danger: true, visibleWhen: { field: "status", equals: "open" } },
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
    name: "hostel/blocks", module: "hostel", label: t("Blocks", "ब्लॉक"), perm: "hostel.block",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "code", label: t("Code", "कोड") },
      { key: "name", label: t("Block", "ब्लॉक") },
      { key: "gender", label: t("For", "हेतु"), type: "tag", options: HOSTEL_GENDER },
      { key: "rooms", label: t("Rooms", "कमरे"), type: "number" },
      { key: "beds", label: t("Beds", "बिस्तर"), type: "number" },
      { key: "occupied", label: t("Occupied", "भरे"), type: "number" },
    ],
    fields: [
      { name: "code", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "gender", label: t("For", "हेतु"), type: "select", options: HOSTEL_GENDER },
      { name: "warden", label: t("Warden", "वार्डन"), type: "relation", relation: STAFF_REL },
    ],
  },
  {
    name: "hostel/rooms", module: "hostel", label: t("Rooms", "कमरे"), perm: "hostel.room",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [
      { field: "block", label: t("Block", "ब्लॉक"), relation: { resource: "hostel/blocks", label: "name" } },
      { field: "has_space", label: t("Beds", "बिस्तर"), options: [opt("true", "With a free bed", "खाली बिस्तर"), opt("false", "Full / unavailable", "भरे / अनुपलब्ध")] },
      { field: "status", label: t("Status", "स्थिति"), options: ROOM_STATUS },
    ],
    columns: [
      { key: "label", label: t("Room", "कमरा") },
      { key: "block_name", label: t("Block", "ब्लॉक") },
      { key: "floor", label: t("Floor", "तल"), type: "number", sorter: true },
      { key: "room_type", label: t("Type", "प्रकार"), type: "tag", options: ROOM_TYPE },
      { key: "gender", label: t("For", "हेतु"), type: "tag", options: HOSTEL_GENDER },
      { key: "capacity", label: t("Beds", "बिस्तर"), type: "number" },
      { key: "occupied", label: t("Occupied", "भरे"), type: "number" },
      { key: "available_beds", label: t("Free", "खाली"), type: "number" },
      { key: "open_repairs", label: t("Open repairs", "लंबित मरम्मत"), type: "number" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: ROOM_STATUS },
    ],
    fields: [
      { name: "block", label: t("Block", "ब्लॉक"), type: "relation", relation: { resource: "hostel/blocks", label: "name" }, required: true },
      { name: "number", label: t("Room number", "कमरा संख्या"), type: "text", required: true },
      { name: "floor", label: t("Floor", "तल"), type: "number" },
      { name: "capacity", label: t("Beds", "बिस्तर"), type: "number", required: true },
      { name: "room_type", label: t("Type", "प्रकार"), type: "select", options: ROOM_TYPE },
      { name: "gender", label: t("For (if different from the block)", "हेतु (ब्लॉक से अलग हो तो)"), type: "select", options: HOSTEL_GENDER },
      { name: "status", label: t("Status", "स्थिति"), type: "select", options: ROOM_STATUS },
    ],
  },
  {
    name: "hostel/allocations", module: "hostel", label: t("Residents", "निवासी"), perm: "hostel.allocation",
    searchable: true, canCreate: true,
    filters: [
      { field: "active", label: t("Current", "वर्तमान"), options: [opt("true", "Current residents", "वर्तमान निवासी"), opt("false", "Past stays", "पूर्व")] },
      { field: "block", label: t("Block", "ब्लॉक"), relation: { resource: "hostel/blocks", label: "name" } },
    ],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "room_label", label: t("Room", "कमरा") },
      { key: "block_name", label: t("Block", "ब्लॉक") },
      { key: "guardian_phone", label: t("Guardian phone", "अभिभावक फ़ोन") },
      { key: "check_in_date", label: t("Check-in", "प्रवेश"), type: "date", sorter: true },
      { key: "check_out_date", label: t("Check-out", "प्रस्थान"), type: "date" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "room", label: t("Room (with a free bed)", "कमरा (खाली बिस्तर वाला)"), type: "relation", relation: { resource: "hostel/rooms", label: "label", search: true }, required: true },
      { name: "check_in_date", label: t("Check-in date", "प्रवेश तिथि"), type: "date" },
      { name: "mess_plan", label: t("Mess plan", "मेस योजना"), type: "select", options: MESS_PLAN, help: t("The resident joins the block's mess", "निवासी ब्लॉक के मेस में जुड़ेगा") },
    ],
    actions: [
      { key: "vacate", label: t("Vacate", "खाली करें"), perm: "hostel.allocation.vacate", method: "post", path: "vacate", danger: true,
        prompt: { field: "reason", label: t("Reason for leaving", "छोड़ने का कारण") }, visibleWhen: { field: "check_out_date", equals: null } },
    ],
  },
  {
    name: "hostel/waitlist", module: "hostel", label: t("Waiting list", "प्रतीक्षा सूची"), perm: "hostel.waitlist",
    canCreate: true, canDelete: true, deleteLabel: t("Cancel", "रद्द करें"),
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: [opt("waiting", "Waiting", "प्रतीक्षा में"), opt("offered", "Bed offered", "बिस्तर प्रस्तावित")] }],
    columns: [
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "room_label", label: t("Room", "कमरा") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "created_at", label: t("Added", "जोड़ा गया"), type: "datetime" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "room", label: t("Room", "कमरा"), type: "relation", relation: { resource: "hostel/rooms", label: "label", search: true }, required: true },
    ],
  },
  {
    name: "hostel/maintenance", module: "hostel", label: t("Repairs", "मरम्मत"), perm: "hostel.maintenance",
    canCreate: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: [opt("open", "Open", "खुला"), opt("closed", "Closed", "बंद")] }],
    columns: [
      { key: "room_label", label: t("Room", "कमरा") },
      { key: "summary", label: t("Problem", "समस्या") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "action_taken", label: t("Action taken", "की गई कार्रवाई") },
      { key: "created_at", label: t("Raised", "दर्ज"), type: "datetime" },
      { key: "closed_at", label: t("Closed", "बंद"), type: "datetime" },
    ],
    fields: [
      { name: "room", label: t("Room", "कमरा"), type: "relation", relation: { resource: "hostel/rooms", label: "label", search: true }, required: true },
      { name: "summary", label: t("Problem", "समस्या"), type: "text", required: true },
      { name: "details", label: t("Details", "विवरण"), type: "textarea" },
    ],
    actions: [
      { key: "close", label: t("Close", "बंद करें"), perm: "hostel.maintenance.manage", method: "post", path: "close",
        prompt: { field: "action_taken", label: t("Action taken", "की गई कार्रवाई") }, visibleWhen: { field: "status", equals: "open" } },
    ],
  },
  {
    name: "hostel/fee-rules", module: "hostel", label: t("Hostel fees", "छात्रावास शुल्क"), perm: "hostel.feerule",
    canCreate: true, canEdit: true, canDelete: true, exportable: false,
    columns: [
      { key: "block_name", label: t("Block (blank = all)", "ब्लॉक (रिक्त = सभी)") },
      { key: "room_type", label: t("Room type (blank = any)", "कमरा प्रकार"), type: "tag", options: ROOM_TYPE },
      { key: "monthly_amount", label: t("Per month", "प्रति माह"), type: "money" },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "block", label: t("Block (leave blank for all blocks)", "ब्लॉक (सभी के लिए रिक्त)"), type: "relation", relation: { resource: "hostel/blocks", label: "name" } },
      { name: "room_type", label: t("Room type (leave blank for any)", "कमरा प्रकार (किसी के लिए रिक्त)"), type: "select", options: ROOM_TYPE },
      { name: "monthly_amount", label: t("Hostel fee per month (₹)", "प्रति माह शुल्क (₹)"), type: "money", required: true },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean" },
    ],
  },
  // ---- mess
  {
    name: "hostel/messes", module: "hostel", label: t("Messes", "मेस"), perm: "hostel.mess",
    canCreate: true, canEdit: true, exportable: false,
    columns: [
      { key: "name", label: t("Mess", "मेस") },
      { key: "contractor_name", label: t("Contractor", "ठेकेदार") },
      { key: "monthly_charge", label: t("Monthly", "मासिक"), type: "money" },
      { key: "per_day_rate", label: t("Per day", "प्रति दिन"), type: "money" },
      { key: "rebate_min_days", label: t("Rebate after (days)", "छूट (न्यूनतम दिन)"), type: "number" },
      { key: "rebate_per_day", label: t("Rebate / day", "छूट / दिन"), type: "money" },
      { key: "members", label: t("Members", "सदस्य"), type: "number" },
    ],
    fields: [
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "blocks", label: t("Blocks it serves", "सेवित ब्लॉक"), type: "multiselect", relation: { resource: "hostel/blocks", label: "name" } },
      { name: "contractor_name", label: t("Contractor", "ठेकेदार"), type: "text" },
      { name: "contractor_phone", label: t("Contractor phone", "ठेकेदार फ़ोन"), type: "text" },
      { name: "monthly_charge", label: t("Fixed monthly charge (₹)", "निश्चित मासिक शुल्क (₹)"), type: "money" },
      { name: "per_day_rate", label: t("Per-day rate (₹)", "प्रति दिन दर (₹)"), type: "money" },
      { name: "rebate_min_days", label: t("Rebate for leave of at least (days)", "न्यूनतम अवकाश दिन (छूट हेतु)"), type: "number" },
      { name: "rebate_per_day", label: t("Rebate per day of leave (₹)", "प्रति अवकाश दिन छूट (₹)"), type: "money" },
      { name: "guest_meal_rate", label: t("Guest meal rate (₹)", "अतिथि भोजन दर (₹)"), type: "money" },
      { name: "meal_rates", label: t("Contractor rate per plate", "ठेकेदार दर प्रति थाली"), type: "rows", addLabel: t("Add meal rate", "दर जोड़ें"), rowFields: [
        { name: "meal", label: t("Meal", "भोजन"), type: "select", options: MEAL, required: true },
        { name: "rate", label: t("Rate (₹)", "दर (₹)"), type: "money", required: true },
      ] },
    ],
    actions: [
      { key: "menu", label: t("Print menu", "मेनू प्रिंट"), perm: "hostel.mess.view", method: "link", path: "", href: "/api/proxy/hostel/messes/{id}/menu-pdf", newTab: true },
    ],
  },
  {
    name: "hostel/menu", module: "hostel", label: t("Weekly menu", "साप्ताहिक मेनू"), perm: "hostel.menu",
    canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "mess", label: t("Mess", "मेस"), relation: { resource: "hostel/messes", label: "name" } }],
    columns: [
      { key: "day", label: t("Day", "दिन"), type: "tag", options: WEEKDAY },
      { key: "meal", label: t("Meal", "भोजन"), type: "tag", options: MEAL },
      { key: "items", label: t("Items", "व्यंजन") },
      { key: "items_hi", label: t("Items (Hindi)", "व्यंजन (हिन्दी)") },
      { key: "is_veg", label: t("Veg", "शाकाहारी"), type: "bool" },
    ],
    fields: [
      { name: "mess", label: t("Mess", "मेस"), type: "relation", relation: { resource: "hostel/messes", label: "name" }, required: true },
      { name: "day", label: t("Day", "दिन"), type: "select", options: WEEKDAY, required: true },
      { name: "meal", label: t("Meal", "भोजन"), type: "select", options: MEAL, required: true },
      { name: "items", label: t("Items", "व्यंजन"), type: "text", required: true },
      { name: "items_hi", label: t("Items in Hindi", "हिन्दी में व्यंजन"), type: "text" },
      { name: "is_veg", label: t("Vegetarian", "शाकाहारी"), type: "boolean" },
    ],
  },
  {
    name: "hostel/mess-members", module: "hostel", label: t("Mess members", "मेस सदस्य"), perm: "hostel.messmember",
    searchable: true, canCreate: true,
    filters: [
      { field: "mess", label: t("Mess", "मेस"), relation: { resource: "hostel/messes", label: "name" } },
      { field: "plan", label: t("Plan", "योजना"), options: MESS_PLAN },
      { field: "active", label: t("Current", "वर्तमान"), options: [opt("true", "Current", "वर्तमान"), opt("false", "Left", "छोड़ चुके")] },
    ],
    columns: [
      { key: "name", label: t("Member", "सदस्य") },
      { key: "kind", label: t("Type", "प्रकार"), type: "tag", options: [opt("student", "Student", "छात्र"), opt("staff", "Staff", "कर्मचारी")] },
      { key: "mess_name", label: t("Mess", "मेस") },
      { key: "plan", label: t("Plan", "योजना"), type: "tag", options: MESS_PLAN },
      { key: "start_date", label: t("From", "से"), type: "date" },
      { key: "end_date", label: t("Until", "तक"), type: "date" },
    ],
    fields: [
      { name: "mess", label: t("Mess", "मेस"), type: "relation", relation: { resource: "hostel/messes", label: "name" }, required: true },
      { name: "student", label: t("Student (day scholar)", "छात्र (दिवा छात्र)"), type: "relation", relation: STUDENT_REL, help: t("Choose a student or a staff member", "छात्र या कर्मचारी चुनें") },
      { name: "staff", label: t("Staff", "कर्मचारी"), type: "relation", relation: STAFF_REL },
      { name: "plan", label: t("Plan", "योजना"), type: "select", options: MESS_PLAN, required: true },
      { name: "start_date", label: t("From", "से"), type: "date" },
    ],
    actions: [
      { key: "end", label: t("End membership", "सदस्यता समाप्त"), perm: "hostel.messmember.manage", method: "post", path: "end", danger: true,
        confirm: t("End this mess membership today?", "आज से सदस्यता समाप्त करें?"), visibleWhen: { field: "is_active", equals: true } },
    ],
  },
  {
    name: "hostel/mess-leave", module: "hostel", label: t("Mess leave", "मेस अवकाश"), perm: "hostel.messleave",
    searchable: true, canCreate: true, canDelete: true,
    columns: [
      { key: "member_name", label: t("Member", "सदस्य") },
      { key: "from_date", label: t("From", "से"), type: "date", sorter: true },
      { key: "to_date", label: t("To", "तक"), type: "date" },
      { key: "days", label: t("Days", "दिन"), type: "number" },
      { key: "reason", label: t("Reason", "कारण") },
      { key: "from_outpass", label: t("From outpass", "आउटपास से"), type: "bool" },
    ],
    fields: [
      { name: "member", label: t("Member", "सदस्य"), type: "relation", relation: { resource: "hostel/mess-members", label: "name", search: true }, required: true },
      { name: "from_date", label: t("From", "से"), type: "date", required: true },
      { name: "to_date", label: t("To", "तक"), type: "date", required: true },
      { name: "reason", label: t("Reason", "कारण"), type: "text" },
    ],
  },
  {
    name: "hostel/guest-meals", module: "hostel", label: t("Guest meals", "अतिथि भोजन"), perm: "hostel.guestmeal",
    canCreate: true,
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "member_name", label: t("Member", "सदस्य") },
      { key: "meal", label: t("Meal", "भोजन"), type: "tag", options: MEAL },
      { key: "count", label: t("Guests", "अतिथि"), type: "number" },
      { key: "guest_name", label: t("Guest", "अतिथि नाम") },
      { key: "amount", label: t("Charged", "शुल्क"), type: "money" },
    ],
    fields: [
      { name: "member", label: t("Member", "सदस्य"), type: "relation", relation: { resource: "hostel/mess-members", label: "name", search: true }, required: true },
      { name: "date", label: t("Date", "तिथि"), type: "date", required: true },
      { name: "meal", label: t("Meal", "भोजन"), type: "select", options: MEAL, required: true },
      { name: "count", label: t("Number of guests", "अतिथियों की संख्या"), type: "number", required: true },
      { name: "guest_name", label: t("Guest name", "अतिथि नाम"), type: "text" },
    ],
  },
  {
    name: "hostel/meal-counts", module: "hostel", label: t("Plates served", "परोसी थालियाँ"), perm: "hostel.mealcount",
    canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "mess", label: t("Mess", "मेस"), relation: { resource: "hostel/messes", label: "name" } }],
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "meal", label: t("Meal", "भोजन"), type: "tag", options: MEAL },
      { key: "served", label: t("Plates", "थालियाँ"), type: "number" },
    ],
    fields: [
      { name: "mess", label: t("Mess", "मेस"), type: "relation", relation: { resource: "hostel/messes", label: "name" }, required: true },
      { name: "date", label: t("Date", "तिथि"), type: "date", required: true },
      { name: "meal", label: t("Meal", "भोजन"), type: "select", options: MEAL, required: true },
      { name: "served", label: t("Plates served", "परोसी थालियाँ"), type: "number", required: true },
    ],
  },
  {
    name: "hostel/mess-rebates", module: "hostel", label: t("Rebate register", "छूट रजिस्टर"), perm: "hostel.messrebate",
    columns: [
      { key: "month", label: t("Leave month", "अवकाश माह"), type: "date" },
      { key: "member_name", label: t("Member", "सदस्य") },
      { key: "leave_from", label: t("Leave from", "अवकाश से"), type: "date" },
      { key: "leave_to", label: t("Leave to", "अवकाश तक"), type: "date" },
      { key: "days", label: t("Days", "दिन"), type: "number" },
      { key: "amount", label: t("Rebate", "छूट"), type: "money" },
    ],
  },
  {
    name: "hostel/mess-complaints", module: "hostel", label: t("Mess complaints", "मेस शिकायतें"), perm: "hostel.complaint",
    canCreate: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: [opt("open", "Open", "खुला"), opt("closed", "Closed", "बंद")] }],
    columns: [
      { key: "created_at", label: t("Raised", "दर्ज"), type: "datetime", sorter: true },
      { key: "mess_name", label: t("Mess", "मेस") },
      { key: "member_name", label: t("By", "द्वारा") },
      { key: "category", label: t("About", "विषय"), type: "tag", options: COMPLAINT_CATEGORY },
      { key: "description", label: t("Complaint", "शिकायत") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "action_taken", label: t("Action taken", "की गई कार्रवाई") },
    ],
    fields: [
      { name: "mess", label: t("Mess", "मेस"), type: "relation", relation: { resource: "hostel/messes", label: "name" }, required: true },
      { name: "member", label: t("Member (optional)", "सदस्य (वैकल्पिक)"), type: "relation", relation: { resource: "hostel/mess-members", label: "name", search: true } },
      { name: "category", label: t("About", "विषय"), type: "select", options: COMPLAINT_CATEGORY, required: true },
      { name: "description", label: t("Complaint", "शिकायत"), type: "textarea", required: true },
    ],
    actions: [
      { key: "close", label: t("Close", "बंद करें"), perm: "hostel.complaint.manage", method: "post", path: "close",
        prompt: { field: "action_taken", label: t("Action taken", "की गई कार्रवाई") }, visibleWhen: { field: "status", equals: "open" } },
    ],
  },
  // ---- gate
  {
    name: "hostel/visitors", module: "hostel", label: t("Approved visitors", "स्वीकृत आगंतुक"), perm: "hostel.visitor",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "name", label: t("Visitor", "आगंतुक") },
      { key: "relation", label: t("Relation", "संबंध") },
      { key: "phone", label: t("Phone", "फ़ोन") },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "name", label: t("Visitor name", "आगंतुक नाम"), type: "text", required: true },
      { name: "relation", label: t("Relation", "संबंध"), type: "text", required: true },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text", required: true },
    ],
  },
  {
    name: "hostel/visits", module: "hostel", label: t("Visitor log", "आगंतुक रजिस्टर"), perm: "hostel.visit",
    searchable: true, canCreate: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: VISIT_STATUS }],
    columns: [
      { key: "created_at", label: t("Arrived", "आगमन"), type: "datetime", sorter: true },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "name", label: t("Visitor", "आगंतुक") },
      { key: "relation", label: t("Relation", "संबंध") },
      { key: "id_proof", label: t("ID proof", "पहचान पत्र") },
      { key: "on_approved_list", label: t("Approved list", "स्वीकृत सूची"), type: "bool" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: VISIT_STATUS },
      { key: "time_in", label: t("In", "प्रवेश"), type: "datetime" },
      { key: "time_out", label: t("Out", "निकास"), type: "datetime" },
    ],
    fields: [
      { name: "student", label: t("Visiting student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "visitor", label: t("Approved visitor (if on the list)", "स्वीकृत आगंतुक (सूची में हो तो)"), type: "relation", relation: { resource: "hostel/visitors", label: "name", search: true } },
      { name: "name", label: t("Visitor name", "आगंतुक नाम"), type: "text" },
      { name: "relation", label: t("Relation", "संबंध"), type: "text" },
      { name: "phone", label: t("Phone", "फ़ोन"), type: "text" },
      { name: "id_proof", label: t("ID proof", "पहचान पत्र"), type: "text" },
      { name: "purpose", label: t("Purpose", "उद्देश्य"), type: "text" },
    ],
    actions: [
      { key: "approve", label: t("Let in", "प्रवेश दें"), perm: "hostel.visit.approve", method: "post", path: "approve", visibleWhen: { field: "status", equals: "held" } },
      { key: "refuse", label: t("Refuse", "मना करें"), perm: "hostel.visit.approve", method: "post", path: "refuse", danger: true, visibleWhen: { field: "status", equals: "held" } },
      { key: "leave", label: t("Mark left", "निकास दर्ज"), perm: "hostel.visit.manage", method: "post", path: "leave", visibleWhen: { field: "status", equals: "in" } },
    ],
  },
  {
    name: "hostel/outpasses", module: "hostel", label: t("Outpasses", "आउटपास"), perm: "hostel.outpass",
    searchable: true, canCreate: true,
    filters: [
      { field: "status", label: t("Status", "स्थिति"), options: OUTPASS_STATUS },
      { field: "is_late", label: t("Late return", "देर से वापसी"), options: [opt("true", "Late only", "केवल देर से")] },
    ],
    columns: [
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "from_date", label: t("From", "से"), type: "date", sorter: true },
      { key: "to_date", label: t("Back by", "वापसी"), type: "date" },
      { key: "days", label: t("Days", "दिन"), type: "number" },
      { key: "reason", label: t("Reason", "कारण") },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: OUTPASS_STATUS },
      { key: "checked_out_at", label: t("Left", "गए"), type: "datetime" },
      { key: "checked_in_at", label: t("Returned", "लौटे"), type: "datetime" },
      { key: "is_late", label: t("Late", "देर"), type: "bool" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "from_date", label: t("Leaving on", "जाने की तिथि"), type: "date", required: true },
      { name: "to_date", label: t("Returning on", "वापसी तिथि"), type: "date", required: true },
      { name: "destination", label: t("Going to", "गंतव्य"), type: "text" },
      { name: "reason", label: t("Reason", "कारण"), type: "text", required: true },
      { name: "requested_by", label: t("Requested by", "अनुरोधकर्ता"), type: "select", options: [opt("parent", "Parent", "अभिभावक"), opt("student", "Student", "छात्र"), opt("warden", "Warden", "वार्डन")] },
    ],
    actions: [
      { key: "approve", label: t("Approve", "स्वीकृत करें"), perm: "hostel.outpass.approve", method: "post", path: "approve", visibleWhen: { field: "status", equals: "requested" } },
      { key: "reject", label: t("Reject", "अस्वीकार करें"), perm: "hostel.outpass.approve", method: "post", path: "reject", danger: true,
        prompt: { field: "note", label: t("Reason", "कारण") }, visibleWhen: { field: "status", equals: "requested" } },
      { key: "out", label: t("Gate: out", "गेट: बाहर"), perm: "hostel.outpass.gate", method: "post", path: "out", visibleWhen: { field: "status", equals: "approved" } },
      { key: "back", label: t("Gate: back", "गेट: वापस"), perm: "hostel.outpass.gate", method: "post", path: "back", visibleWhen: { field: "status", equals: "out" } },
    ],
  },

  // ------------------------------------------------------------ attendance
  {
    name: "attendance/records", module: "attendance", label: t("Attendance records", "उपस्थिति अभिलेख"), perm: "attendance.record",
    searchable: true,
    filters: [
      { field: "section", label: t("Section", "अनुभाग"), relation: SECTION_REL },
      { field: "status", label: t("Status", "स्थिति"), options: ATT_STATUS },
      { field: "source", label: t("Source", "स्रोत"), options: [opt("manual", "Teacher", "शिक्षक"), opt("device", "Device", "उपकरण")] },
    ],
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "section_name", label: t("Section", "अनुभाग") },
      { key: "period", label: t("Lecture", "व्याख्यान"), type: "number" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag", options: ATT_STATUS },
      { key: "source", label: t("Source", "स्रोत"), type: "tag", options: [opt("manual", "Teacher", "शिक्षक"), opt("device", "Device", "उपकरण")] },
      { key: "marked_by", label: t("Marked by", "द्वारा") },
    ],
  },
  {
    name: "attendance/holidays", module: "attendance", label: t("Holidays", "अवकाश"), perm: "attendance.holiday",
    canCreate: true, canEdit: true, canDelete: true, defaultSort: { field: "date", order: "asc" },
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "name", label: t("Holiday", "अवकाश") },
      { key: "name_hi", label: t("In Hindi", "हिन्दी में") },
    ],
    fields: [
      { name: "date", label: t("Date", "तिथि"), type: "date", required: true },
      { name: "name", label: t("Holiday", "अवकाश"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
    ],
  },
  {
    name: "attendance/devices", module: "attendance", label: t("Attendance devices", "उपस्थिति उपकरण"), perm: "attendance.device",
    canCreate: true, canEdit: true, canDelete: true, exportable: false,
    columns: [
      { key: "name", label: t("Device", "उपकरण") },
      { key: "brand", label: t("Brand / connection", "ब्रांड / कनेक्शन"), type: "tag", options: DEVICE_BRAND },
      { key: "serial_no", label: t("Serial no.", "सीरियल सं.") },
      { key: "location", label: t("Location", "स्थान") },
      { key: "push_url", label: t("How it connects", "कैसे जुड़ता है") },
      { key: "token", label: t("Device key (JSON push)", "डिवाइस कुंजी") },
      { key: "last_seen_at", label: t("Last seen", "अंतिम संपर्क"), type: "datetime" },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "brand", label: t("Brand / connection", "ब्रांड / कनेक्शन"), type: "select", options: DEVICE_BRAND, required: true },
      { name: "model", label: t("Model", "मॉडल"), type: "text" },
      { name: "serial_no", label: t("Serial number (as on the device)", "सीरियल संख्या"), type: "text", required: true },
      { name: "location", label: t("Location", "स्थान"), type: "text" },
      { name: "allowed_ips", label: t("Allowed IP addresses (optional)", "अनुमत IP (वैकल्पिक)"), type: "text" },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean" },
    ],
    actions: [
      { key: "rotate", label: t("New key", "नई कुंजी"), perm: "attendance.device.manage", method: "post", path: "rotate-key",
        confirm: t("Issue a new device key? The old key stops working.", "नई कुंजी जारी करें? पुरानी कुंजी बंद हो जाएगी।") },
    ],
  },
  {
    name: "attendance/cards", module: "attendance", label: t("Cards & device IDs", "कार्ड एवं डिवाइस आईडी"), perm: "attendance.card",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "code", label: t("Card / user code", "कार्ड / उपयोगकर्ता कोड") },
      { key: "person", label: t("Student / staff", "छात्र / कर्मचारी") },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "code", label: t("Card number or device user ID", "कार्ड संख्या या डिवाइस आईडी"), type: "text", required: true },
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, help: t("Choose a student or a staff member", "छात्र या कर्मचारी चुनें") },
      { name: "staff", label: t("Staff", "कर्मचारी"), type: "relation", relation: STAFF_REL },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean" },
    ],
  },
  {
    name: "attendance/punches", module: "attendance", label: t("Device punches", "उपकरण पंच"), perm: "attendance.punch",
    searchable: true, importable: true,
    filters: [{ field: "source", label: t("Source", "स्रोत"), options: [opt("push", "Device", "उपकरण"), opt("import", "File import", "फ़ाइल आयात")] }],
    columns: [
      { key: "punched_at", label: t("Time", "समय"), type: "datetime", sorter: true },
      { key: "code", label: t("Code", "कोड") },
      { key: "person", label: t("Student / staff", "छात्र / कर्मचारी") },
      { key: "device_name", label: t("Device", "उपकरण") },
      { key: "source", label: t("Source", "स्रोत"), type: "tag" },
    ],
  },
  {
    name: "attendance/settings", module: "attendance", label: t("Attendance settings", "उपस्थिति सेटिंग्स"), perm: "attendance.settings",
    canEdit: true, exportable: false,
    columns: [
      { key: "mode", label: t("Marking", "चिह्नांकन"), type: "tag", options: ATT_MODE },
      { key: "weekly_off", label: t("Weekly off (0=Mon … 6=Sun)", "साप्ताहिक अवकाश") },
      { key: "threshold_percent", label: t("Minimum %", "न्यूनतम %"), type: "number" },
      { key: "long_absence_days", label: t("Long absence after (days)", "लंबी अनुपस्थिति (दिन)"), type: "number" },
      { key: "auto_mark_from_punches", label: t("Device punches mark present", "पंच से उपस्थित"), type: "bool" },
    ],
    fields: [
      { name: "mode", label: t("Marking", "चिह्नांकन"), type: "select", options: ATT_MODE, required: true },
      { name: "weekly_off", label: t("Weekly off days (0=Mon … 6=Sun, comma separated)", "साप्ताहिक अवकाश (0=सोम … 6=रवि)"), type: "text", required: true },
      { name: "threshold_percent", label: t("Minimum attendance %", "न्यूनतम उपस्थिति %"), type: "number", required: true },
      { name: "long_absence_days", label: t("Flag long absence after (days)", "लंबी अनुपस्थिति (दिन)"), type: "number", required: true },
      { name: "auto_mark_from_punches", label: t("A device punch marks the student present", "पंच से छात्र उपस्थित"), type: "boolean" },
    ],
  },

  // ------------------------------------------------------------ exam
  {
    name: "exam/exams", module: "exam", label: t("Exams", "परीक्षाएँ"), perm: "exam.setup",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), relation: { resource: "people/programs", label: "name" } }],
    columns: [
      { key: "name", label: t("Exam", "परीक्षा") },
      { key: "program_name", label: t("Class / course", "कक्षा / पाठ्यक्रम") },
      { key: "scale_name", label: t("Grading", "ग्रेडिंग") },
      { key: "weightage", label: t("Weightage %", "भारांक %"), type: "number" },
      { key: "subject_count", label: t("Subjects", "विषय"), type: "number" },
      { key: "is_published", label: t("Published", "प्रकाशित"), type: "bool" },
    ],
    fields: [
      { name: "name", label: t("Exam name (e.g. Half-Yearly)", "परीक्षा नाम (उदा. अर्धवार्षिक)"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "academic_year", label: t("Academic year", "शैक्षणिक वर्ष"), type: "relation", relation: { resource: "people/academic-years", label: "name" }, required: true },
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" }, required: true },
      { name: "term", label: t("Term / semester (colleges)", "सत्र / सेमेस्टर"), type: "relation", relation: { resource: "people/terms", label: "name" } },
      { name: "scale", label: t("Grading", "ग्रेडिंग"), type: "relation", relation: { resource: "exam/scales", label: "name" }, required: true },
      { name: "weightage", label: t("Weightage in the final result (%)", "अंतिम परिणाम में भारांक (%)"), type: "number" },
      { name: "sequence", label: t("Order", "क्रम"), type: "number" },
      { name: "is_term_final", label: t("Semester-end exam (counts for SGPA/CGPA)", "सेमेस्टर-अंत परीक्षा (SGPA/CGPA)"), type: "boolean" },
    ],
    actions: [
      { key: "datesheet", label: t("Date sheet", "डेट शीट"), perm: "exam.setup.view", method: "link", path: "", href: "/api/proxy/exam/exams/{id}/date-sheet", newTab: true },
      { key: "publish", label: t("Publish results", "परिणाम प्रकाशित करें"), perm: "exam.result.publish", method: "post", path: "publish",
        confirm: t("Publish results to parents and students?", "परिणाम अभिभावकों व छात्रों को प्रकाशित करें?"), visibleWhen: { field: "is_published", equals: false } },
      { key: "unpublish", label: t("Unpublish", "अप्रकाशित करें"), perm: "exam.result.publish", method: "post", path: "unpublish", danger: true,
        visibleWhen: { field: "is_published", equals: true } },
    ],
  },
  {
    name: "exam/exam-subjects", module: "exam", label: t("Exam subjects & date sheet", "परीक्षा विषय एवं डेट शीट"), perm: "exam.setup",
    canCreate: true, canEdit: true, canDelete: true,
    filters: [{ field: "exam", label: t("Exam", "परीक्षा"), relation: { resource: "exam/exams", label: "label", search: true } }],
    columns: [
      { key: "exam_name", label: t("Exam", "परीक्षा") },
      { key: "subject_name", label: t("Subject", "विषय") },
      { key: "max_theory", label: t("Theory", "सैद्धांतिक"), type: "number" },
      { key: "max_practical", label: t("Practical", "प्रायोगिक"), type: "number" },
      { key: "pass_marks", label: t("Pass marks", "उत्तीर्णांक"), type: "number" },
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "start_time", label: t("Starts", "आरंभ") },
    ],
    fields: [
      { name: "exam", label: t("Exam", "परीक्षा"), type: "relation", relation: { resource: "exam/exams", label: "label", search: true }, required: true },
      { name: "subject", label: t("Subject", "विषय"), type: "relation", relation: { resource: "people/subjects", label: "name", search: true }, required: true },
      { name: "max_theory", label: t("Theory max", "सैद्धांतिक पूर्णांक"), type: "number", required: true },
      { name: "max_practical", label: t("Practical max (0 if none)", "प्रायोगिक पूर्णांक (न हो तो 0)"), type: "number" },
      { name: "pass_marks", label: t("Pass marks", "उत्तीर्णांक"), type: "number", required: true },
      { name: "date", label: t("Exam date", "परीक्षा तिथि"), type: "date" },
      { name: "start_time", label: t("Start time (HH:MM)", "आरंभ समय (HH:MM)"), type: "text" },
      { name: "duration_minutes", label: t("Duration (minutes)", "अवधि (मिनट)"), type: "number" },
      { name: "sequence", label: t("Order", "क्रम"), type: "number" },
    ],
  },
  {
    name: "exam/scales", module: "exam", label: t("Grading scales", "ग्रेडिंग पैमाने"), perm: "exam.setup",
    canCreate: true, canEdit: true, exportable: false,
    columns: [
      { key: "name", label: t("Scale", "पैमाना") },
      { key: "kind", label: t("Type", "प्रकार"), type: "tag", options: SCALE_KIND },
    ],
    fields: [
      { name: "name", label: t("Name (e.g. CBSE 8-point)", "नाम"), type: "text", required: true },
      { name: "kind", label: t("Type", "प्रकार"), type: "select", options: SCALE_KIND, required: true },
      { name: "bands", label: t("Grade bands", "ग्रेड श्रेणियाँ"), type: "rows", required: true, addLabel: t("Add band", "श्रेणी जोड़ें"), rowFields: [
        { name: "grade", label: t("Grade", "ग्रेड"), type: "text", required: true },
        { name: "min_percent", label: t("From %", "से %"), type: "number", required: true },
        { name: "grade_point", label: t("Grade point", "ग्रेड पॉइंट"), type: "number" },
        { name: "is_fail", label: t("Fail", "अनुत्तीर्ण"), type: "boolean" },
      ] },
    ],
  },

  // ------------------------------------------------------------ fees
  {
    name: "fees/accounts", module: "fees", label: t("Dues & defaulters", "बकाया एवं चूककर्ता"), perm: "fees.account",
    searchable: true,
    filters: [
      { field: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), relation: { resource: "people/programs", label: "name" } },
      { field: "section", label: t("Section", "अनुभाग"), relation: SECTION_REL },
      { field: "overdue", label: t("Show", "दिखाएँ"), options: [opt("true", "Overdue only (defaulters)", "केवल चूककर्ता"), opt("false", "Everyone", "सभी")] },
    ],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "full_name", label: t("Student", "छात्र"), sorter: true },
      { key: "program", label: t("Class", "कक्षा") },
      { key: "section", label: t("Section", "अनुभाग") },
      { key: "guardian_name", label: t("Guardian", "अभिभावक") },
      { key: "guardian_phone", label: t("Guardian phone", "अभिभावक फ़ोन") },
      { key: "total_charged", label: t("Charged", "देय"), type: "money" },
      { key: "total_paid", label: t("Paid", "भुगतान"), type: "money" },
      { key: "outstanding", label: t("Outstanding", "बकाया"), type: "money", sorter: true },
      { key: "overdue", label: t("Overdue", "अतिदेय"), type: "money", sorter: true },
    ],
    actions: [
      { key: "collect", label: t("Collect", "जमा करें"), perm: "fees.receipt.manage", method: "link", path: "", href: "/fees/collect?student={id}" },
    ],
  },
  {
    name: "fees/receipts", module: "fees", label: t("Receipts", "रसीदें"), perm: "fees.receipt",
    searchable: true,
    filters: [{ field: "mode", label: t("Mode", "माध्यम"), options: [
      opt("cash", "Cash", "नकद"), opt("cheque", "Cheque", "चेक"), opt("dd", "Demand draft", "डिमांड ड्राफ्ट"),
      opt("upi", "UPI", "UPI"), opt("bank_transfer", "Bank transfer", "बैंक हस्तांतरण")] },
      { field: "cancelled", label: t("Status", "स्थिति"), options: [opt("false", "Valid", "मान्य"), opt("true", "Cancelled", "रद्द")] }],
    columns: [
      { key: "number", label: t("Receipt no.", "रसीद सं.") },
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "mode", label: t("Mode", "माध्यम"), type: "tag" },
      { key: "reference", label: t("Reference", "संदर्भ") },
      { key: "amount", label: t("Amount", "राशि"), type: "money", sorter: true },
      { key: "is_cancelled", label: t("Cancelled", "रद्द"), type: "bool" },
    ],
    actions: [
      { key: "print", label: t("Print", "प्रिंट"), perm: "fees.receipt.view", method: "link", path: "", href: "/api/proxy/fees/receipts/{id}/pdf", newTab: true },
      { key: "cancel", label: t("Cancel", "रद्द करें"), perm: "fees.receipt.cancel", method: "post", path: "cancel", danger: true,
        prompt: { field: "reason", label: t("Reason for cancelling", "रद्द करने का कारण") }, visibleWhen: { field: "is_cancelled", equals: false } },
    ],
  },
  {
    name: "fees/charges", module: "fees", label: t("Student charges", "छात्र देय"), perm: "fees.charge",
    searchable: true, canCreate: true, createEndpoint: "fees/charges/adjust",
    filters: [
      { field: "head", label: t("Fee head", "शुल्क मद"), relation: { resource: "fees/heads", label: "name" } },
      { field: "source_type", label: t("Source", "स्रोत"), options: [
        opt("plan", "Fee plan", "शुल्क योजना"), opt("hostel", "Hostel", "छात्रावास"), opt("mess", "Mess", "मेस"), opt("guest_meal", "Guest meal", "अतिथि भोजन"),
        opt("transport", "Transport", "परिवहन"), opt("library", "Library", "पुस्तकालय"), opt("late_fine", "Late fine", "विलंब शुल्क"),
        opt("manual", "Manual", "मैनुअल")] },
    ],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "head_name", label: t("Head", "मद") },
      { key: "description", label: t("Description", "विवरण") },
      { key: "due_date", label: t("Due", "नियत तिथि"), type: "date", sorter: true },
      { key: "net", label: t("Amount", "राशि"), type: "money" },
      { key: "paid", label: t("Paid", "भुगतान"), type: "money" },
      { key: "outstanding", label: t("Outstanding", "बकाया"), type: "money" },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "head", label: t("Fee head", "शुल्क मद"), type: "relation", relation: { resource: "fees/heads", label: "name" }, required: true },
      { name: "amount", label: t("Amount (₹, negative for a credit note)", "राशि (₹, क्रेडिट के लिए ऋणात्मक)"), type: "number", required: true },
      { name: "description", label: t("Description", "विवरण"), type: "text", required: true },
      { name: "due_date", label: t("Due date", "नियत तिथि"), type: "date" },
    ],
  },
  {
    name: "fees/concessions", module: "fees", label: t("Concessions", "रियायतें"), perm: "fees.concession",
    searchable: true, canCreate: true,
    filters: [{ field: "status", label: t("Status", "स्थिति"), options: [
      opt("pending", "Waiting for approval", "स्वीकृति हेतु"), opt("approved", "Approved", "स्वीकृत"), opt("rejected", "Rejected", "अस्वीकृत")] }],
    columns: [
      { key: "admission_no", label: t("Admission no.", "प्रवेश सं.") },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "head_name", label: t("Head", "मद") },
      { key: "kind", label: t("Type", "प्रकार"), type: "tag", options: [opt("percent", "%", "%"), opt("fixed", "Fixed ₹", "निश्चित ₹")] },
      { key: "value", label: t("Value", "मान"), type: "number" },
      { key: "reason", label: t("Reason", "कारण"), type: "tag" },
      { key: "status", label: t("Status", "स्थिति"), type: "tag" },
      { key: "decided_by", label: t("Decided by", "निर्णयकर्ता") },
    ],
    fields: [
      { name: "student", label: t("Student", "छात्र"), type: "relation", relation: STUDENT_REL, required: true },
      { name: "head", label: t("Fee head", "शुल्क मद"), type: "relation", relation: { resource: "fees/heads", label: "name" }, required: true },
      { name: "academic_year", label: t("Academic year", "शैक्षणिक वर्ष"), type: "relation", relation: { resource: "people/academic-years", label: "name" }, required: true },
      { name: "kind", label: t("Type", "प्रकार"), type: "select", options: [opt("percent", "Percentage", "प्रतिशत"), opt("fixed", "Fixed amount per instalment", "प्रति किस्त निश्चित राशि")], required: true },
      { name: "value", label: t("Value (% or ₹)", "मान (% या ₹)"), type: "number", required: true },
      { name: "reason", label: t("Reason", "कारण"), type: "select", required: true, options: [
        opt("sibling", "Sibling", "भाई-बहन"), opt("staff_ward", "Staff ward", "कर्मचारी आश्रित"), opt("merit", "Merit", "मेधा"),
        opt("rte", "RTE", "RTE"), opt("other", "Other", "अन्य")] },
      { name: "note", label: t("Note", "टिप्पणी"), type: "text" },
    ],
    actions: [
      { key: "approve", label: t("Approve", "स्वीकृत करें"), perm: "fees.concession.approve", method: "post", path: "approve", visibleWhen: { field: "status", equals: "pending" } },
      { key: "reject", label: t("Reject", "अस्वीकार करें"), perm: "fees.concession.approve", method: "post", path: "reject", danger: true, visibleWhen: { field: "status", equals: "pending" } },
    ],
  },
  {
    name: "fees/plans", module: "fees", label: t("Fee plans", "शुल्क योजनाएँ"), perm: "fees.plan",
    searchable: true, canCreate: true, canEdit: true, canDelete: true,
    columns: [
      { key: "name", label: t("Plan", "योजना") },
      { key: "program_name", label: t("Class / course", "कक्षा / पाठ्यक्रम") },
      { key: "head_name", label: t("Head", "मद") },
      { key: "total", label: t("Total per student", "प्रति छात्र कुल"), type: "money" },
    ],
    fields: [
      { name: "name", label: t("Plan name", "योजना नाम"), type: "text", required: true },
      { name: "academic_year", label: t("Academic year", "शैक्षणिक वर्ष"), type: "relation", relation: { resource: "people/academic-years", label: "name" }, required: true },
      { name: "program", label: t("Class / course", "कक्षा / पाठ्यक्रम"), type: "relation", relation: { resource: "people/programs", label: "name" }, required: true },
      { name: "term", label: t("Term / semester (optional)", "सत्र / सेमेस्टर (वैकल्पिक)"), type: "relation", relation: { resource: "people/terms", label: "name" } },
      { name: "head", label: t("Fee head", "शुल्क मद"), type: "relation", relation: { resource: "fees/heads", label: "name" }, required: true },
      { name: "instalments", label: t("Instalments", "किस्तें"), type: "rows", required: true, addLabel: t("Add instalment", "किस्त जोड़ें"), rowFields: [
        { name: "sequence", label: t("No.", "क्रम"), type: "number", required: true },
        { name: "label", label: t("Label (e.g. Q1 Apr–Jun)", "नाम (उदा. Q1)"), type: "text", required: true },
        { name: "due_date", label: t("Due date", "नियत तिथि"), type: "date", required: true },
        { name: "amount", label: t("Amount (₹)", "राशि (₹)"), type: "money", required: true },
      ] },
    ],
    actions: [
      { key: "apply", label: t("Bill enrolled students", "नामांकित छात्रों पर लागू करें"), perm: "fees.plan.manage", method: "post", path: "apply",
        confirm: t("Add this plan's instalments to every enrolled student who doesn't have them yet?", "यह योजना सभी नामांकित छात्रों पर लागू करें?") },
    ],
  },
  {
    name: "fees/heads", module: "fees", label: t("Fee heads", "शुल्क मद"), perm: "fees.head",
    searchable: true, canCreate: true, canEdit: true,
    columns: [
      { key: "code", label: t("Code", "कोड") },
      { key: "name", label: t("Name", "नाम") },
      { key: "kind", label: t("Type", "प्रकार"), type: "tag" },
      { key: "late_fine_mode", label: t("Late fine", "विलंब शुल्क"), type: "tag" },
      { key: "late_fine_amount", label: t("Fine (₹)", "शुल्क (₹)"), type: "money" },
      { key: "grace_days", label: t("Grace days", "छूट दिन"), type: "number" },
      { key: "is_active", label: t("Active", "सक्रिय"), type: "bool" },
    ],
    fields: [
      { name: "code", label: t("Code", "कोड"), type: "text", required: true },
      { name: "name", label: t("Name", "नाम"), type: "text", required: true },
      { name: "name_hi", label: t("Name in Hindi", "हिन्दी में नाम"), type: "text" },
      { name: "kind", label: t("Type", "प्रकार"), type: "select", options: [
        opt("tuition", "Tuition", "शिक्षण"), opt("admission", "Admission", "प्रवेश"), opt("exam", "Exam", "परीक्षा"),
        opt("development", "Development", "विकास"), opt("transport", "Transport", "परिवहन"), opt("hostel", "Hostel", "छात्रावास"),
        opt("mess", "Mess", "मेस"), opt("library_fine", "Library fine", "पुस्तकालय जुर्माना"),
        opt("late_fine", "Late fine", "विलंब शुल्क"), opt("other", "Other", "अन्य")] },
      { name: "late_fine_mode", label: t("Late fine", "विलंब शुल्क"), type: "select", options: [
        opt("none", "No late fine", "कोई नहीं"), opt("per_day", "Per day", "प्रति दिन"), opt("flat", "Flat", "एकमुश्त")] },
      { name: "late_fine_amount", label: t("Late fine amount (₹)", "विलंब शुल्क राशि (₹)"), type: "money" },
      { name: "grace_days", label: t("Grace days after due date", "नियत तिथि के बाद छूट दिन"), type: "number" },
      { name: "tally_ledger", label: t("Tally income ledger", "टैली आय खाता"), type: "text" },
      { name: "is_active", label: t("Active", "सक्रिय"), type: "boolean" },
    ],
  },
  {
    name: "fees/refunds", module: "fees", label: t("Refunds", "धनवापसी"), perm: "fees.refund",
    searchable: false,
    columns: [
      { key: "date", label: t("Date", "तिथि"), type: "date", sorter: true },
      { key: "student_name", label: t("Student", "छात्र") },
      { key: "mode", label: t("Mode", "माध्यम"), type: "tag" },
      { key: "amount", label: t("Amount", "राशि"), type: "money" },
      { key: "reason", label: t("Reason", "कारण") },
      { key: "created_by", label: t("By", "द्वारा") },
    ],
  },
  {
    name: "fees/settings", module: "fees", label: t("Fee settings", "शुल्क सेटिंग्स"), perm: "fees.settings",
    canEdit: true, exportable: false,
    columns: [
      { key: "receipt_prefix", label: t("Receipt prefix", "रसीद उपसर्ग") },
      { key: "cash_ledger", label: t("Tally cash ledger", "टैली नकद खाता") },
      { key: "bank_ledger", label: t("Tally bank ledger", "टैली बैंक खाता") },
      { key: "tally_company", label: t("Tally company", "टैली कंपनी") },
    ],
    fields: [
      { name: "receipt_prefix", label: t("Receipt prefix", "रसीद उपसर्ग"), type: "text", required: true },
      { name: "cash_ledger", label: t("Tally cash ledger", "टैली नकद खाता"), type: "text", required: true },
      { name: "bank_ledger", label: t("Tally bank ledger", "टैली बैंक खाता"), type: "text", required: true },
      { name: "tally_company", label: t("Tally company name", "टैली कंपनी नाम"), type: "text" },
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

export const PAGES: PageDef[] = [
  { name: "attendance/mark", module: "attendance", label: t("Mark attendance", "उपस्थिति लगाएँ"), perm: "attendance.record.mark", path: "/attendance/mark" },
  { name: "attendance/reports-page", module: "attendance", label: t("Attendance reports", "उपस्थिति रिपोर्ट"), perm: "attendance.report.view", path: "/attendance/reports" },
  { name: "exam/marks-page", module: "exam", label: t("Enter marks", "अंक दर्ज करें"), perm: "exam.marks.enter", path: "/exam/marks" },
  { name: "exam/results-page", module: "exam", label: t("Results & report cards", "परिणाम एवं रिपोर्ट कार्ड"), perm: "exam.result.view", path: "/exam/results" },
  { name: "fees/collect", module: "fees", label: t("Collect fees", "शुल्क जमा"), perm: "fees.receipt.manage", path: "/fees/collect" },
  { name: "fees/reports-page", module: "fees", label: t("Fee reports", "शुल्क रिपोर्ट"), perm: "fees.report.view", path: "/fees/reports" },
];

export function findResource(module: string, resource: string): ResourceDef | undefined {
  return RESOURCES.find((r) => r.name === `${module}/${resource}`);
}

export const tr = (text: T, lang: "en" | "hi") => text[lang] || text.en;
