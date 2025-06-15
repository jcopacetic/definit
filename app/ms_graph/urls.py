from django.urls import path 

from app.ms_graph.views import excel_note_to_hubspot

app_name = "ms_graph"

urlpatterns = [
    path("excel-note-to-hubspot/<slug:excel_row>/", view=excel_note_to_hubspot, name="excel-note-to-hubspot"),
]