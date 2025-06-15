from django.urls import path 

from app.ms_graph.views import excel_note_to_hubspot

app_name = "ms_graph"

urlpatterns = [
    # Changed to accept any string parameter (signed value)
    path("excel-note-to-hubspot/<str:signed_row>/", view=excel_note_to_hubspot, name="excel-note-to-hubspot"),
]